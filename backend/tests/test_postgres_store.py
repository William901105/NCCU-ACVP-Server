from __future__ import annotations

from app.storage.postgres_store import connect, init_db, reset_db_for_tests


def test_postgres_db_init_creates_required_tables() -> None:
    reset_db_for_tests()
    init_db()

    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        ).fetchall()
    finally:
        conn.close()

    table_names = {row["table_name"] for row in rows}
    assert {
        "imports",
        "demo_sessions",
        "acvp_sessions",
        "acvp_vector_sets",
        "acvp_requests",
        "state_events",
    }.issubset(table_names)
