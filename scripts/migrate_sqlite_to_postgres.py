from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Sequence

import psycopg
from psycopg import sql


TABLES: tuple[str, ...] = (
    "imports",
    "demo_sessions",
    "acvp_sessions",
    "acvp_vector_sets",
    "acvp_requests",
    "state_events",
)

IDENTITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("acvp_requests", "request_id"),
    ("state_events", "id"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate NCCU ACVP Server data from SQLite to PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        required=True,
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--database-url",
        default=(
            os.environ.get("DATABASE_URL")
            or os.environ.get("ACVP_DATABASE_URL")
        ),
        help=(
            "PostgreSQL connection URL. Defaults to DATABASE_URL or "
            "ACVP_DATABASE_URL."
        ),
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Delete existing PostgreSQL rows before migration.",
    )
    return parser.parse_args()


def sqlite_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    }


def sqlite_columns(
    connection: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def postgres_columns(
    connection: psycopg.Connection,
    table: str,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def table_count(
    connection: psycopg.Connection,
    table: str,
) -> int:
    row = connection.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(
            sql.Identifier(table)
        )
    ).fetchone()
    assert row is not None
    return int(row[0])


def ensure_target_is_safe(
    connection: psycopg.Connection,
    *,
    truncate_target: bool,
) -> None:
    non_empty = {
        table: table_count(connection, table)
        for table in TABLES
        if table_count(connection, table) > 0
    }

    if non_empty and not truncate_target:
        details = ", ".join(
            f"{table}={count}"
            for table, count in non_empty.items()
        )
        raise RuntimeError(
            "PostgreSQL target is not empty. "
            f"Existing rows: {details}. "
            "Use --truncate-target only when replacement is intended."
        )

    if truncate_target:
        identifiers = sql.SQL(", ").join(
            sql.Identifier(table)
            for table in reversed(TABLES)
        )
        connection.execute(
            sql.SQL(
                "TRUNCATE TABLE {} RESTART IDENTITY CASCADE"
            ).format(identifiers)
        )


def migrate_table(
    sqlite_connection: sqlite3.Connection,
    postgres_connection: psycopg.Connection,
    table: str,
) -> int:
    source_columns = sqlite_columns(sqlite_connection, table)
    target_columns = postgres_columns(postgres_connection, table)

    if not target_columns:
        raise RuntimeError(
            f"PostgreSQL table does not exist: {table}"
        )

    unsupported = [
        column
        for column in source_columns
        if column not in target_columns
    ]
    if unsupported:
        raise RuntimeError(
            f"PostgreSQL table {table} is missing source columns: "
            + ", ".join(unsupported)
        )

    selected_columns = [
        column
        for column in target_columns
        if column in source_columns
    ]

    column_sql = ", ".join(
        f'"{column}"'
        for column in selected_columns
    )
    rows: Sequence[sqlite3.Row] = sqlite_connection.execute(
        f'SELECT {column_sql} FROM "{table}"'
    ).fetchall()

    if not rows:
        return 0

    insert_query = sql.SQL(
        "INSERT INTO {} ({}) VALUES ({})"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(
            sql.Identifier(column)
            for column in selected_columns
        ),
        sql.SQL(", ").join(
            sql.Placeholder()
            for _ in selected_columns
        ),
    )

    postgres_connection.cursor().executemany(
        insert_query,
        [tuple(row[column] for column in selected_columns) for row in rows],
    )
    return len(rows)


def synchronize_sequences(
    connection: psycopg.Connection,
) -> None:
    for table, column in IDENTITY_COLUMNS:
        connection.execute(
            sql.SQL(
                """
                SELECT setval(
                    pg_get_serial_sequence(%s, %s),
                    COALESCE(MAX({column}), 1),
                    MAX({column}) IS NOT NULL
                )
                FROM {table}
                """
            ).format(
                table=sql.Identifier(table),
                column=sql.Identifier(column),
            ),
            (table, column),
        )


def verify_counts(
    sqlite_connection: sqlite3.Connection,
    postgres_connection: psycopg.Connection,
) -> None:
    mismatches: list[str] = []

    for table in TABLES:
        source_count = int(
            sqlite_connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
        )
        target_count = table_count(postgres_connection, table)

        if source_count != target_count:
            mismatches.append(
                f"{table}: SQLite={source_count}, "
                f"PostgreSQL={target_count}"
            )

    if mismatches:
        raise RuntimeError(
            "Migration count verification failed: "
            + "; ".join(mismatches)
        )


def main() -> int:
    args = parse_args()
    sqlite_path = args.sqlite_path.expanduser().resolve()

    if not sqlite_path.is_file():
        raise FileNotFoundError(
            f"SQLite database does not exist: {sqlite_path}"
        )

    if not args.database_url:
        raise RuntimeError(
            "PostgreSQL URL is required through --database-url, "
            "DATABASE_URL, or ACVP_DATABASE_URL."
        )

    with sqlite3.connect(str(sqlite_path)) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        sqlite_connection.execute("PRAGMA foreign_keys = ON")

        missing_tables = set(TABLES) - sqlite_tables(sqlite_connection)
        if missing_tables:
            raise RuntimeError(
                "SQLite source is missing required tables: "
                + ", ".join(sorted(missing_tables))
            )

        with psycopg.connect(args.database_url) as postgres_connection:
            ensure_target_is_safe(
                postgres_connection,
                truncate_target=args.truncate_target,
            )

            migrated: dict[str, int] = {}
            for table in TABLES:
                migrated[table] = migrate_table(
                    sqlite_connection,
                    postgres_connection,
                    table,
                )

            synchronize_sequences(postgres_connection)
            verify_counts(sqlite_connection, postgres_connection)

    print("SQLite to PostgreSQL migration completed.")
    for table in TABLES:
        print(f"  {table}: {migrated[table]} rows")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
