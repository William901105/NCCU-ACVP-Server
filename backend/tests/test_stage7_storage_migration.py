from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from app.storage.sqlite_store import (
    create_acvp_request,
    get_acvp_request,
    get_acvp_session,
    get_acvp_vector_set_by_vs_id,
    get_db_path,
    init_db,
)


LEGACY_SCHEMA = """
CREATE TABLE acvp_sessions (
    test_session_id TEXT PRIMARY KEY, label TEXT, status TEXT NOT NULL,
    vector_set_ids_json TEXT NOT NULL, registration_json TEXT,
    negotiated_capabilities_json TEXT, production_ready INTEGER NOT NULL DEFAULT 0,
    profile TEXT NOT NULL DEFAULT 'local-fips204-skeleton',
    demo_only INTEGER NOT NULL DEFAULT 1, not_production_acvp INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT, extra_json TEXT
);
CREATE TABLE acvp_vector_sets (
    vector_set_id TEXT PRIMARY KEY, test_session_id TEXT NOT NULL, status TEXT NOT NULL,
    algorithm TEXT, mode TEXT, revision TEXT, prompt_json TEXT NOT NULL,
    expected_results_json TEXT NOT NULL, response_json TEXT, validation_result_json TEXT,
    report_json TEXT, downloaded_at TEXT, submitted_at TEXT, validated_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, extra_json TEXT,
    FOREIGN KEY(test_session_id) REFERENCES acvp_sessions(test_session_id) ON DELETE CASCADE
);
"""


def create_legacy_database(*, prompt: Any, extra: Any = None) -> tuple[str, str]:
    path = get_db_path()
    path.unlink(missing_ok=True)
    session_id = "legacy-session"
    vector_id = "11111111-2222-3333-4444-555555555555"
    now = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(
            """
            INSERT INTO acvp_sessions (
                test_session_id, label, status, vector_set_ids_json,
                created_at, updated_at, extra_json
            ) VALUES (?, NULL, 'vectorReady', ?, ?, ?, '{}')
            """,
            (session_id, json.dumps([vector_id]), now, now),
        )
        conn.execute(
            """
            INSERT INTO acvp_vector_sets (
                vector_set_id, test_session_id, status, algorithm, mode, revision,
                prompt_json, expected_results_json, created_at, updated_at, extra_json
            ) VALUES (?, ?, 'vectorReady', 'ML-KEM', 'keyGen', 'FIPS203', ?, '{}', ?, ?, ?)
            """,
            (vector_id, session_id, json.dumps(prompt), now, now, json.dumps(extra or {})),
        )
    return session_id, vector_id


def insert_legacy_session(conn: sqlite3.Connection, session_id: str, vector_ids: list[str]) -> None:
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO acvp_sessions (
            test_session_id, label, status, vector_set_ids_json,
            created_at, updated_at, extra_json
        ) VALUES (?, NULL, 'vectorReady', ?, ?, ?, '{}')
        """,
        (session_id, json.dumps(vector_ids), now, now),
    )


def insert_legacy_vector(
    conn: sqlite3.Connection,
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
            vector_set_id, test_session_id, status, algorithm, mode, revision,
            prompt_json, expected_results_json, created_at, updated_at, extra_json
        ) VALUES (?, ?, 'vectorReady', 'ML-KEM', 'keyGen', 'FIPS203', ?, '{}', ?, ?, '{}')
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
    assert session is not None and session["vectorSetIds"] == [vector_id]
    assert vector is not None
    assert vector["vectorSetId"] == vector_id
    assert vector["vsId"] == 73

    with sqlite3.connect(str(get_db_path())) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(acvp_vector_sets)")}
        assert "vs_id" in columns
        assert columns["vector_set_id"][5] == 1
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(acvp_vector_sets)")}
        assert "uq_acvp_vector_sets_session_vs_id" in indexes

    request = create_acvp_request(
        session_id,
        {"moduleUrl": "/acvp/v1/modules/1", "oeUrl": "/acvp/v1/oes/1"},
    )
    init_db()
    assert get_acvp_request(request["requestId"])["testSessionId"] == session_id


def test_migration_can_backfill_from_legacy_extra() -> None:
    session_id, _ = create_legacy_database(
        prompt={"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"},
        extra={"vsId": 19},
    )
    init_db()
    assert get_acvp_vector_set_by_vs_id(session_id, 19)["vsId"] == 19


def test_malformed_legacy_vector_record_fails_with_explicit_error() -> None:
    _, vector_id = create_legacy_database(
        prompt={"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}
    )
    with pytest.raises(RuntimeError, match="valid numeric vsId") as exc_info:
        init_db()
    assert vector_id in str(exc_info.value)


def test_legacy_duplicate_vs_ids_in_same_session_fail_migration() -> None:
    path = get_db_path()
    path.unlink(missing_ok=True)
    session_id = "duplicate-session"
    vector_ids = ["legacy-vector-one", "legacy-vector-two"]
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(LEGACY_SCHEMA)
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

    with sqlite3.connect(str(path)) as conn:
        rows = conn.execute(
            "SELECT vector_set_id, test_session_id, prompt_json FROM acvp_vector_sets"
        ).fetchall()
    assert {row[0] for row in rows} == set(vector_ids)
    assert {row[1] for row in rows} == {session_id}
    assert {json.loads(row[2])["vsId"] for row in rows} == {41}


def test_legacy_same_vs_id_in_different_sessions_migrates() -> None:
    path = get_db_path()
    path.unlink(missing_ok=True)
    records = [
        ("legacy-session-one", "legacy-vector-one"),
        ("legacy-session-two", "legacy-vector-two"),
    ]
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(LEGACY_SCHEMA)
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
