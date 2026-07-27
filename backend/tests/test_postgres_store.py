from __future__ import annotations

from app.storage.postgres_store import (
    connect,
    get_acvp_vector_set,
    init_db,
    reset_db_for_tests,
    save_acvp_session,
    save_acvp_vector_set,
)


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
        "acvp_reports",
        "acvp_requests",
        "state_events",
    }.issubset(table_names)

def test_acvp_reports_are_stored_in_independent_table() -> None:
    session_id = "report-session"
    vector_set_id = "report-vector"

    save_acvp_session(
        {
            "testSessionId": session_id,
            "status": "complete",
            "vectorSetIds": [vector_set_id],
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-01T00:00:00+00:00",
        }
    )

    artifacts = [
        {
            "schemaVersion": "1.0",
            "artifactType": "nccu-acvp-validation-report",
            "reportId": "REPORT-001",
            "generatedAt": "2026-01-01T00:01:00+00:00",
            "testSessionId": session_id,
            "vsId": 7,
            "disposition": "failed",
            "passed": False,
            "publishable": False,
            "responseSha256": "a" * 64,
            "artifactSha256": "b" * 64,
        },
        {
            "schemaVersion": "1.0",
            "artifactType": "nccu-acvp-validation-report",
            "reportId": "REPORT-002",
            "generatedAt": "2026-01-01T00:02:00+00:00",
            "testSessionId": session_id,
            "vsId": 7,
            "disposition": "passed",
            "passed": True,
            "publishable": True,
            "responseSha256": "c" * 64,
            "artifactSha256": "d" * 64,
        },
    ]

    save_acvp_vector_set(
        {
            "vectorSetId": vector_set_id,
            "testSessionId": session_id,
            "vsId": 7,
            "status": "complete",
            "prompt": {
                "vsId": 7,
                "algorithm": "ML-DSA",
                "mode": "keyGen",
                "revision": "FIPS204",
                "testGroups": [],
            },
            "expectedResults": {
                "vsId": 7,
                "algorithm": "ML-DSA",
                "mode": "keyGen",
                "revision": "FIPS204",
                "testGroups": [],
            },
            "report": {
                "schemaVersion": "1.0",
                "artifactType": "nccu-acvp-validation-report",
                "latestReportId": "REPORT-002",
                "artifacts": artifacts,
            },
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-01T00:02:00+00:00",
        }
    )

    conn = connect()
    try:
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
            SELECT report_id, is_latest
            FROM acvp_reports
            WHERE vector_set_id = ?
            ORDER BY report_sequence
            """,
            (vector_set_id,),
        ).fetchall()
    finally:
        conn.close()

    assert "report_json" not in vector_columns
    assert [
        (row["report_id"], row["is_latest"])
        for row in report_rows
    ] == [
        ("REPORT-001", 0),
        ("REPORT-002", 1),
    ]

    stored = get_acvp_vector_set(vector_set_id)
    assert stored is not None
    assert stored["report"]["latestReportId"] == "REPORT-002"
    assert stored["report"]["artifacts"] == artifacts
