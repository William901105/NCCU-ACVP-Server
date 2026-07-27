from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
import pytest

from app.storage.postgres_store import (
    create_acvp_request,
    get_acvp_request,
    get_acvp_session,
    get_acvp_vector_set_by_vs_id,
    get_database_url,
    init_db,
)


LEGACY_SCHEMA = """
CREATE TABLE acvp_sessions (
    test_session_id TEXT PRIMARY KEY,
    label TEXT,
    status TEXT NOT NULL,
    vector_set_ids_json TEXT NOT NULL,
    registration_json TEXT,
    negotiated_capabilities_json TEXT,
    production_ready INTEGER NOT NULL DEFAULT 0,
    profile TEXT NOT NULL DEFAULT 'local-fips204-skeleton',
    demo_only INTEGER NOT NULL DEFAULT 1,
    not_production_acvp INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    extra_json TEXT
);

CREATE TABLE acvp_vector_sets (
    vector_set_id TEXT PRIMARY KEY,
    test_session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    algorithm TEXT,
    mode TEXT,
    revision TEXT,
    prompt_json TEXT NOT NULL,
    expected_results_json TEXT NOT NULL,
    response_json TEXT,
    validation_result_json TEXT,
    report_json TEXT,
    downloaded_at TEXT,
    submitted_at TEXT,
    validated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra_json TEXT,
    FOREIGN KEY(test_session_id)
        REFERENCES acvp_sessions(test_session_id)
        ON DELETE CASCADE
);
"""


def _connect(*, autocommit: bool = True):
    return psycopg.connect(
        get_database_url(),
        autocommit=autocommit,
        row_factory=dict_row,
    )


def _create_legacy_schema(conn: Any) -> None:
    for statement in LEGACY_SCHEMA.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)


def _drop_current_schema(conn: Any) -> None:
    for table in (
        "state_events",
        "acvp_requests",
        "acvp_reports",
        "acvp_vector_sets",
        "acvp_sessions",
        "demo_sessions",
        "imports",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def create_legacy_database(
    *,
    prompt: Any,
    extra: Any = None,
) -> tuple[str, str]:
    session_id = "legacy-session"
    vector_id = "11111111-2222-3333-4444-555555555555"
    now = "2026-01-01T00:00:00+00:00"

    with _connect() as conn:
        _drop_current_schema(conn)
        _create_legacy_schema(conn)

        conn.execute(
            """
            INSERT INTO acvp_sessions (
                test_session_id,
                label,
                status,
                vector_set_ids_json,
                created_at,
                updated_at,
                extra_json
            ) VALUES (%s, NULL, 'vectorReady', %s, %s, %s, '{}')
            """,
            (session_id, json.dumps([vector_id]), now, now),
        )

        conn.execute(
            """
            INSERT INTO acvp_vector_sets (
                vector_set_id,
                test_session_id,
                status,
                algorithm,
                mode,
                revision,
                prompt_json,
                expected_results_json,
                created_at,
                updated_at,
                extra_json
            ) VALUES (
                %s,
                %s,
                'vectorReady',
                'ML-KEM',
                'keyGen',
                'FIPS203',
                %s,
                '{}',
                %s,
                %s,
                %s
            )
            """,
            (
                vector_id,
                session_id,
                json.dumps(prompt),
                now,
                now,
                json.dumps(extra or {}),
            ),
        )

    return session_id, vector_id


def insert_legacy_session(
    conn: Any,
    session_id: str,
    vector_ids: list[str],
) -> None:
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO acvp_sessions (
            test_session_id,
            label,
            status,
            vector_set_ids_json,
            created_at,
            updated_at,
            extra_json
        ) VALUES (%s, NULL, 'vectorReady', %s, %s, %s, '{}')
        """,
        (session_id, json.dumps(vector_ids), now, now),
    )


def insert_legacy_vector(
    conn: Any,
    *,
    session_id: str,
    vector_id: str,
    vs_id: int,
) -> None:
    now = "2026-01-01T00:00:00+00:00"
    prompt = {
        "vsId": vs_id,
        "algorithm": "ML-KEM",
        "mode": "keyGen",
        "revision": "FIPS203",
        "testGroups": [],
    }

    conn.execute(
        """
        INSERT INTO acvp_vector_sets (
            vector_set_id,
            test_session_id,
            status,
            algorithm,
            mode,
            revision,
            prompt_json,
            expected_results_json,
            created_at,
            updated_at,
            extra_json
        ) VALUES (
            %s,
            %s,
            'vectorReady',
            'ML-KEM',
            'keyGen',
            'FIPS203',
            %s,
            '{}',
            %s,
            %s,
            '{}'
        )
        """,
        (vector_id, session_id, json.dumps(prompt), now, now),
    )


def test_stage6_database_is_migrated_additively_and_idempotently() -> None:
    session_id, vector_id = create_legacy_database(
        prompt={
            "vsId": 73,
            "algorithm": "ML-KEM",
            "mode": "keyGen",
            "revision": "FIPS203",
            "testGroups": [],
        }
    )

    init_db()
    init_db()

    session = get_acvp_session(session_id)
    vector = get_acvp_vector_set_by_vs_id(session_id, 73)

    assert session is not None
    assert session["vectorSetIds"] == [vector_id]
    assert vector is not None
    assert vector["vectorSetId"] == vector_id
    assert vector["vsId"] == 73

    with _connect() as conn:
        columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'acvp_vector_sets'
                """
            ).fetchall()
        }
        assert "vs_id" in columns

        primary_key_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = 'acvp_vector_sets'
                  AND tc.constraint_type = 'PRIMARY KEY'
                """
            ).fetchall()
        }
        assert primary_key_columns == {"vector_set_id"}

        indexes = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'acvp_vector_sets'
                """
            ).fetchall()
        }
        assert "uq_acvp_vector_sets_session_vs_id" in indexes

    request = create_acvp_request(
        session_id,
        {
            "moduleUrl": "/acvp/v1/modules/1",
            "oeUrl": "/acvp/v1/oes/1",
        },
    )
    init_db()

    persisted = get_acvp_request(request["requestId"])
    assert persisted is not None
    assert persisted["testSessionId"] == session_id


def test_migration_can_backfill_from_legacy_extra() -> None:
    session_id, _ = create_legacy_database(
        prompt={
            "algorithm": "ML-KEM",
            "mode": "keyGen",
            "revision": "FIPS203",
        },
        extra={"vsId": 19},
    )

    init_db()

    vector = get_acvp_vector_set_by_vs_id(session_id, 19)
    assert vector is not None
    assert vector["vsId"] == 19


def test_malformed_legacy_vector_record_fails_with_explicit_error() -> None:
    _, vector_id = create_legacy_database(
        prompt={
            "algorithm": "ML-KEM",
            "mode": "keyGen",
            "revision": "FIPS203",
        }
    )

    with pytest.raises(RuntimeError, match="valid numeric vsId") as exc_info:
        init_db()

    assert vector_id in str(exc_info.value)


def test_legacy_duplicate_vs_ids_in_same_session_fail_migration() -> None:
    session_id = "duplicate-session"
    vector_ids = ["legacy-vector-one", "legacy-vector-two"]

    with _connect() as conn:
        _drop_current_schema(conn)
        _create_legacy_schema(conn)
        insert_legacy_session(conn, session_id, vector_ids)

        for vector_id in vector_ids:
            insert_legacy_vector(
                conn,
                session_id=session_id,
                vector_id=vector_id,
                vs_id=41,
            )

    with pytest.raises(RuntimeError, match="duplicate numeric vsId"):
        init_db()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT vector_set_id, test_session_id, prompt_json
            FROM acvp_vector_sets
            """
        ).fetchall()

    assert {row["vector_set_id"] for row in rows} == set(vector_ids)
    assert {row["test_session_id"] for row in rows} == {session_id}
    assert {
        json.loads(row["prompt_json"])["vsId"]
        for row in rows
    } == {41}


def test_legacy_same_vs_id_in_different_sessions_migrates() -> None:
    records = [
        ("legacy-session-one", "legacy-vector-one"),
        ("legacy-session-two", "legacy-vector-two"),
    ]

    with _connect() as conn:
        _drop_current_schema(conn)
        _create_legacy_schema(conn)

        for session_id, vector_id in records:
            insert_legacy_session(conn, session_id, [vector_id])
            insert_legacy_vector(
                conn,
                session_id=session_id,
                vector_id=vector_id,
                vs_id=41,
            )

    init_db()

    for session_id, vector_id in records:
        vector = get_acvp_vector_set_by_vs_id(session_id, 41)
        assert vector is not None
        assert vector["vectorSetId"] == vector_id

def test_legacy_report_json_migrates_to_acvp_reports() -> None:
    session_id, vector_id = create_legacy_database(
        prompt={
            "vsId": 23,
            "algorithm": "ML-KEM",
            "mode": "keyGen",
            "revision": "FIPS203",
            "testGroups": [],
        }
    )

    artifact = {
        "schemaVersion": "1.0",
        "artifactType": "nccu-acvp-validation-report",
        "reportId": "LEGACY-REPORT-001",
        "generatedAt": "2026-01-01T00:01:00+00:00",
        "testSessionId": session_id,
        "vsId": 23,
        "disposition": "passed",
        "passed": True,
        "publishable": True,
        "responseSha256": "a" * 64,
        "artifactSha256": "b" * 64,
    }
    report_store = {
        "schemaVersion": "1.0",
        "artifactType": "nccu-acvp-validation-report",
        "latestReportId": artifact["reportId"],
        "artifacts": [artifact],
    }

    with _connect() as conn:
        conn.execute(
            """
            UPDATE acvp_vector_sets
            SET report_json = %s
            WHERE vector_set_id = %s
            """,
            (json.dumps(report_store), vector_id),
        )

    init_db()

    stored = get_acvp_vector_set_by_vs_id(session_id, 23)
    assert stored is not None
    assert stored["report"] == report_store

    with _connect() as conn:
        vector_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'acvp_vector_sets'
                """
            ).fetchall()
        }
        report_rows = conn.execute(
            """
            SELECT report_id, vector_set_id, is_latest, artifact_json
            FROM acvp_reports
            WHERE vector_set_id = %s
            """,
            (vector_id,),
        ).fetchall()

    assert "report_json" not in vector_columns
    assert len(report_rows) == 1
    assert report_rows[0]["report_id"] == artifact["reportId"]
    assert report_rows[0]["vector_set_id"] == vector_id
    assert report_rows[0]["is_latest"] == 1
    assert json.loads(report_rows[0]["artifact_json"]) == artifact
