from __future__ import annotations

import os
import psycopg
from psycopg.rows import dict_row
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, MutableMapping, Optional
from urllib.parse import urlparse

from ..acvp_parser import AcvpParseError, normalize_acvp_json, summarize_vector_set
from .json_utils import json_dumps, json_loads, utc_now_iso


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS imports (
    import_id TEXT PRIMARY KEY,
    label TEXT,
    algorithm TEXT,
    mode TEXT,
    revision TEXT,
    prompt_json TEXT NOT NULL,
    expected_results_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    generated_expected_results INTEGER NOT NULL DEFAULT 0,
    validation_result_json TEXT,
    report_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_sessions (
    session_id TEXT PRIMARY KEY,
    label TEXT,
    status TEXT NOT NULL,
    prompt_json TEXT NOT NULL,
    expected_results_json TEXT,
    response_json TEXT,
    validation_result_json TEXT,
    report_json TEXT,
    import_id TEXT,
    algorithm TEXT,
    mode TEXT,
    revision TEXT,
    vs_id INTEGER,
    test_group_count INTEGER,
    test_case_count INTEGER,
    demo_only INTEGER NOT NULL DEFAULT 1,
    not_production_acvp INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS acvp_sessions (
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

CREATE TABLE IF NOT EXISTS acvp_vector_sets (
    vector_set_id TEXT PRIMARY KEY,
    test_session_id TEXT NOT NULL,
    vs_id INTEGER,
    status TEXT NOT NULL,
    algorithm TEXT,
    mode TEXT,
    revision TEXT,
    prompt_json TEXT NOT NULL,
    expected_results_json TEXT NOT NULL,
    response_json TEXT,
    validation_result_json TEXT,
    downloaded_at TEXT,
    submitted_at TEXT,
    validated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra_json TEXT,
    FOREIGN KEY(test_session_id) REFERENCES acvp_sessions(test_session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS acvp_reports (
    report_sequence BIGSERIAL PRIMARY KEY,
    report_id TEXT NOT NULL UNIQUE,
    vector_set_id TEXT NOT NULL,
    test_session_id TEXT NOT NULL,
    vs_id INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    disposition TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    publishable INTEGER NOT NULL DEFAULT 0,
    is_latest INTEGER NOT NULL DEFAULT 0,
    response_sha256 TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(vector_set_id)
        REFERENCES acvp_vector_sets(vector_set_id) ON DELETE CASCADE,
    FOREIGN KEY(test_session_id)
        REFERENCES acvp_sessions(test_session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS acvp_requests (
    request_id BIGSERIAL PRIMARY KEY,
    test_session_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    certification_json TEXT NOT NULL,
    message TEXT,
    approved_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(test_session_id) REFERENCES acvp_sessions(test_session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS state_events (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    event TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_imports_mode ON imports(mode);
CREATE INDEX IF NOT EXISTS idx_demo_sessions_status ON demo_sessions(status);
CREATE INDEX IF NOT EXISTS idx_acvp_sessions_status ON acvp_sessions(status);
CREATE INDEX IF NOT EXISTS idx_acvp_vector_sets_session ON acvp_vector_sets(test_session_id);
CREATE INDEX IF NOT EXISTS idx_acvp_reports_vector_set
ON acvp_reports(vector_set_id, report_sequence);
CREATE INDEX IF NOT EXISTS idx_acvp_reports_session_vs
ON acvp_reports(test_session_id, vs_id, report_sequence);
ALTER TABLE acvp_reports
ADD COLUMN IF NOT EXISTS is_latest INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_acvp_reports_latest
ON acvp_reports(vector_set_id)
WHERE is_latest = 1;
CREATE INDEX IF NOT EXISTS idx_acvp_requests_session ON acvp_requests(test_session_id);
CREATE INDEX IF NOT EXISTS idx_state_events_entity ON state_events(entity_type, entity_id);
"""


def get_database_url() -> str:
    configured = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("ACVP_DATABASE_URL")
    )
    if not configured:
        raise RuntimeError(
            "DATABASE_URL or ACVP_DATABASE_URL must be configured for PostgreSQL."
        )
    return configured



def _assert_test_database() -> None:
    database_name = urlparse(get_database_url()).path.lstrip("/")
    allowed_name = os.environ.get(
        "ACVP_TEST_DATABASE_NAME",
        "acvp_test",
    )

    if database_name != allowed_name:
        raise RuntimeError(
            "Refusing to reset PostgreSQL database "
            f"{database_name!r}; expected test database {allowed_name!r}."
        )


def _translate_qmark(query: str) -> str:
    return query.replace("?", "%s")


class _ConnectionAdapter:
    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, query: str, params: Any = None):
        translated = _translate_qmark(query)
        if params is None:
            return self._connection.execute(translated)
        return self._connection.execute(translated, params)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _open_connection(*, autocommit: bool = False) -> _ConnectionAdapter:
    connection = psycopg.connect(
        get_database_url(),
        autocommit=autocommit,
        row_factory=dict_row,
    )
    return _ConnectionAdapter(connection)


def init_db() -> None:
    conn = _open_connection(autocommit=True)
    try:
        for statement in SCHEMA_SQL.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        _migrate_public_vs_ids(conn)
        _migrate_report_artifacts(conn)
    finally:
        conn.close()


def _migrate_report_artifacts(conn: _ConnectionAdapter) -> None:
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

    if "report_json" not in columns:
        return

    rows = conn.execute(
        """
        SELECT vector_set_id, test_session_id, vs_id, report_json
        FROM acvp_vector_sets
        WHERE report_json IS NOT NULL
        """
    ).fetchall()

    for row in rows:
        report_store = json_loads(row["report_json"], default=None)
        if not isinstance(report_store, dict):
            raise ValueError(
                "Cannot migrate malformed report_json for vector set "
                f"{row['vector_set_id']!r}"
            )

        _save_acvp_report_store(
            conn,
            {
                "vectorSetId": row["vector_set_id"],
                "testSessionId": row["test_session_id"],
                "vsId": row["vs_id"],
                "report": report_store,
            },
        )

    conn.execute(
        "ALTER TABLE acvp_vector_sets DROP COLUMN report_json"
    )


def reset_db_for_tests() -> None:
    _assert_test_database()
    conn = _open_connection(autocommit=True)
    try:
        conn.execute("DROP TABLE IF EXISTS state_events CASCADE")
        conn.execute("DROP TABLE IF EXISTS acvp_requests CASCADE")
        conn.execute("DROP TABLE IF EXISTS acvp_reports CASCADE")
        conn.execute("DROP TABLE IF EXISTS acvp_vector_sets CASCADE")
        conn.execute("DROP TABLE IF EXISTS acvp_sessions CASCADE")
        conn.execute("DROP TABLE IF EXISTS demo_sessions CASCADE")
        conn.execute("DROP TABLE IF EXISTS imports CASCADE")
    finally:
        conn.close()
    init_db()


def connect() -> _ConnectionAdapter:
    init_db()
    return _open_connection()

def save_acvp_session(session: Dict[str, Any]) -> None:
    now = utc_now_iso()
    session_id = session["testSessionId"]
    vector_set_ids = list(session.get("vectorSetIds", []))
    created_at = session.get("createdAt") or now
    updated_at = session.get("updatedAt") or now
    extra = _extra_fields(session, _ACVP_SESSION_CORE_KEYS)
    values = (
        session.get("label"),
        session["status"],
        json_dumps(vector_set_ids),
        _json_or_none(session.get("registration")),
        _json_or_none(session.get("negotiatedCapabilities")),
        1 if session.get("productionReady", False) else 0,
        session.get("profile", "local-fips204-skeleton"),
        1 if session.get("demoOnly", True) else 0,
        1 if session.get("notProductionAcvp", True) else 0,
        created_at,
        updated_at,
        session.get("expiresAt"),
        json_dumps(extra),
    )
    with _write_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE acvp_sessions
            SET label = ?, status = ?, vector_set_ids_json = ?,
                registration_json = ?, negotiated_capabilities_json = ?,
                production_ready = ?, profile = ?, demo_only = ?,
                not_production_acvp = ?, created_at = ?, updated_at = ?,
                expires_at = ?, extra_json = ?
            WHERE test_session_id = ?
            """,
            (*values, session_id),
        )
        if cursor.rowcount == 0:
            conn.execute(
                """
                INSERT INTO acvp_sessions (
                    test_session_id, label, status, vector_set_ids_json,
                    registration_json, negotiated_capabilities_json,
                    production_ready, profile, demo_only, not_production_acvp,
                    created_at, updated_at, expires_at, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, *values),
            )


def get_acvp_session(test_session_id: str) -> Optional[Dict[str, Any]]:
    with _read_connection() as conn:
        row = conn.execute(
            "SELECT * FROM acvp_sessions WHERE test_session_id = ?",
            (test_session_id,),
        ).fetchone()
    return _row_to_acvp_session(row) if row is not None else None


def list_acvp_sessions(
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM acvp_sessions"
    params: List[Any] = []
    if status is not None:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at, test_session_id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)
    elif offset is not None:
        sql += " LIMIT ALL OFFSET ?"
        params.append(offset)
    with _read_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_acvp_session(row) for row in rows]


def update_acvp_session(test_session_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    session = get_acvp_session(test_session_id)
    if session is None:
        return None
    session.update(fields)
    session["updatedAt"] = fields.get("updatedAt") or utc_now_iso()
    save_acvp_session(session)
    return session


def delete_acvp_session(test_session_id: str) -> bool:
    with _write_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM acvp_sessions WHERE test_session_id = ?",
            (test_session_id,),
        )
        conn.execute(
            "DELETE FROM state_events WHERE entity_type = ? AND entity_id = ?",
            ("acvp_session", test_session_id),
        )
        return cursor.rowcount > 0


def clear_acvp_sessions() -> None:
    with _write_connection() as conn:
        conn.execute("DELETE FROM acvp_sessions")
        conn.execute("DELETE FROM state_events WHERE entity_type = 'acvp_session'")


def _report_artifacts_from_store(report_store: Any) -> List[Dict[str, Any]]:
    if not isinstance(report_store, dict):
        return []

    stored = report_store.get("artifacts")
    if isinstance(stored, list):
        return [
            dict(item)
            for item in stored
            if isinstance(item, dict) and item.get("reportId")
        ]

    if report_store.get("reportId"):
        return [dict(report_store)]

    return []


def _save_acvp_report_store(
    conn: _ConnectionAdapter,
    vector_set: Dict[str, Any],
) -> None:
    vector_set_id = str(vector_set["vectorSetId"])
    report_store = vector_set.get("report")
    artifacts = _report_artifacts_from_store(report_store)

    conn.execute(
        "DELETE FROM acvp_reports WHERE vector_set_id = ?",
        (vector_set_id,),
    )

    if not artifacts:
        return

    latest_report_id = (
        report_store.get("latestReportId")
        if isinstance(report_store, dict)
        else None
    )
    available_ids = {
        str(artifact["reportId"])
        for artifact in artifacts
    }
    if latest_report_id not in available_ids:
        latest_report_id = str(artifacts[-1]["reportId"])

    now = utc_now_iso()

    for artifact in artifacts:
        report_id = str(artifact["reportId"])
        test_session_id = str(
            artifact.get("testSessionId")
            or vector_set["testSessionId"]
        )
        vs_id = artifact.get("vsId", vector_set.get("vsId"))

        if isinstance(vs_id, bool) or not isinstance(vs_id, int) or vs_id < 0:
            raise ValueError(
                f"Report {report_id!r} requires a non-negative numeric vsId"
            )

        conn.execute(
            """
            INSERT INTO acvp_reports (
                report_id, vector_set_id, test_session_id, vs_id,
                schema_version, artifact_type, generated_at,
                disposition, passed, publishable, is_latest,
                response_sha256, artifact_sha256, artifact_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                vector_set_id,
                test_session_id,
                vs_id,
                str(artifact.get("schemaVersion", "")),
                str(artifact.get("artifactType", "")),
                str(artifact.get("generatedAt") or now),
                str(artifact.get("disposition", "error")),
                1 if artifact.get("passed", False) else 0,
                1 if artifact.get("publishable", False) else 0,
                1 if report_id == latest_report_id else 0,
                str(artifact.get("responseSha256", "")),
                str(artifact.get("artifactSha256", "")),
                json_dumps(artifact),
                now,
            ),
        )


def _load_acvp_report_store(
    conn: _ConnectionAdapter,
    vector_set_id: str,
) -> Optional[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT report_id, schema_version, artifact_type,
               artifact_json, is_latest
        FROM acvp_reports
        WHERE vector_set_id = ?
        ORDER BY report_sequence
        """,
        (vector_set_id,),
    ).fetchall()

    artifacts: List[Dict[str, Any]] = []
    latest_report_id: Optional[str] = None
    latest_schema_version = ""
    latest_artifact_type = ""

    for row in rows:
        artifact = json_loads(row["artifact_json"], default=None)
        if not isinstance(artifact, dict):
            continue

        artifacts.append(artifact)
        if row["is_latest"]:
            latest_report_id = row["report_id"]
            latest_schema_version = row["schema_version"]
            latest_artifact_type = row["artifact_type"]

    if not artifacts:
        return None

    if latest_report_id is None:
        latest = rows[-1]
        latest_report_id = latest["report_id"]
        latest_schema_version = latest["schema_version"]
        latest_artifact_type = latest["artifact_type"]

    return {
        "schemaVersion": latest_schema_version,
        "artifactType": latest_artifact_type,
        "latestReportId": latest_report_id,
        "artifacts": artifacts,
    }


def save_acvp_vector_set(vector_set: Dict[str, Any]) -> None:
    now = utc_now_iso()
    prompt = vector_set["prompt"]
    expected_results = vector_set.get("expectedResults")
    summary = _safe_prompt_summary(prompt)
    vs_id = _public_vs_id(vector_set, summary=summary)
    created_at = vector_set.get("createdAt") or now
    updated_at = vector_set.get("updatedAt") or now
    extra = _extra_fields(vector_set, _ACVP_VECTOR_SET_CORE_KEYS)
    values = (
        vector_set["testSessionId"],
        vs_id,
        vector_set["status"],
        summary.get("algorithm"),
        vector_set.get("mode") or summary.get("mode"),
        summary.get("revision"),
        json_dumps(prompt),
        json_dumps(expected_results),
        _json_or_none(vector_set.get("response")),
        _json_or_none(vector_set.get("validationResult")),
        vector_set.get("downloadedAt"),
        vector_set.get("submittedAt"),
        vector_set.get("validatedAt"),
        created_at,
        updated_at,
        json_dumps(extra),
    )
    with _write_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE acvp_vector_sets
            SET test_session_id = ?, vs_id = ?, status = ?, algorithm = ?, mode = ?,
                revision = ?, prompt_json = ?, expected_results_json = ?,
                response_json = ?, validation_result_json = ?,
                downloaded_at = ?, submitted_at = ?, validated_at = ?,
                created_at = ?, updated_at = ?, extra_json = ?
            WHERE vector_set_id = ?
            """,
            (*values, vector_set["vectorSetId"]),
        )
        if cursor.rowcount == 0:
            conn.execute(
                """
                INSERT INTO acvp_vector_sets (
                    vector_set_id, test_session_id, vs_id, status, algorithm, mode, revision,
                    prompt_json, expected_results_json, response_json,
                    validation_result_json, downloaded_at, submitted_at,
                    validated_at, created_at, updated_at, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (vector_set["vectorSetId"], *values),
            )

        _save_acvp_report_store(conn, vector_set)


def get_acvp_vector_set(vector_set_id: str) -> Optional[Dict[str, Any]]:
    with _read_connection() as conn:
        row = conn.execute(
            "SELECT * FROM acvp_vector_sets WHERE vector_set_id = ?",
            (vector_set_id,),
        ).fetchone()
        report_store = (
            _load_acvp_report_store(conn, vector_set_id)
            if row is not None
            else None
        )
    return (
        _row_to_acvp_vector_set(row, report_store=report_store)
        if row is not None
        else None
    )


def get_acvp_vector_set_by_vs_id(
    test_session_id: str,
    vs_id: int,
) -> Optional[Dict[str, Any]]:
    with _read_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM acvp_vector_sets
            WHERE test_session_id = ? AND vs_id = ?
            """,
            (test_session_id, vs_id),
        ).fetchone()
        report_store = (
            _load_acvp_report_store(conn, row["vector_set_id"])
            if row is not None
            else None
        )
    return (
        _row_to_acvp_vector_set(row, report_store=report_store)
        if row is not None
        else None
    )


def list_acvp_vector_sets_for_session(test_session_id: str) -> List[Dict[str, Any]]:
    with _read_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM acvp_vector_sets
            WHERE test_session_id = ?
            ORDER BY created_at, vector_set_id
            """,
            (test_session_id,),
        ).fetchall()
        report_stores = {
            row["vector_set_id"]: _load_acvp_report_store(
                conn,
                row["vector_set_id"],
            )
            for row in rows
        }
    return [
        _row_to_acvp_vector_set(
            row,
            report_store=report_stores[row["vector_set_id"]],
        )
        for row in rows
    ]


def update_acvp_vector_set(vector_set_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    vector_set = get_acvp_vector_set(vector_set_id)
    if vector_set is None:
        return None
    vector_set.update(fields)
    vector_set["updatedAt"] = fields.get("updatedAt") or utc_now_iso()
    save_acvp_vector_set(vector_set)
    return vector_set


def delete_acvp_vector_sets_for_session(test_session_id: str) -> None:
    with _write_connection() as conn:
        rows = conn.execute(
            "SELECT vector_set_id FROM acvp_vector_sets WHERE test_session_id = ?",
            (test_session_id,),
        ).fetchall()
        conn.execute(
            "DELETE FROM acvp_vector_sets WHERE test_session_id = ?",
            (test_session_id,),
        )
        for row in rows:
            conn.execute(
                "DELETE FROM state_events WHERE entity_type = ? AND entity_id = ?",
                ("acvp_vector_set", row["vector_set_id"]),
            )


def delete_acvp_vector_set(vector_set_id: str) -> bool:
    with _write_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM acvp_vector_sets WHERE vector_set_id = ?",
            (vector_set_id,),
        )
        conn.execute(
            "DELETE FROM state_events WHERE entity_type = ? AND entity_id = ?",
            ("acvp_vector_set", vector_set_id),
        )
        return cursor.rowcount > 0


def clear_acvp_vector_sets() -> None:
    with _write_connection() as conn:
        conn.execute("DELETE FROM acvp_vector_sets")
        conn.execute("DELETE FROM state_events WHERE entity_type = 'acvp_vector_set'")


def create_acvp_request(
    test_session_id: str,
    certification: Dict[str, Any],
    *,
    status: str = "initial",
    message: Optional[str] = None,
) -> Dict[str, Any]:
    now = utc_now_iso()
    with _write_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO acvp_requests (
                test_session_id, status, certification_json, message,
                approved_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, ?, ?)
            RETURNING request_id
            """,
            (test_session_id, status, json_dumps(certification), message, now, now),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create ACVP request resource")
        request_id = int(row["request_id"])
    request = get_acvp_request(request_id)
    if request is None:
        raise RuntimeError("Failed to persist ACVP request resource")
    return request


def get_acvp_request(request_id: int) -> Optional[Dict[str, Any]]:
    with _read_connection() as conn:
        row = conn.execute(
            "SELECT * FROM acvp_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    return _row_to_acvp_request(row) if row is not None else None


def get_acvp_request_for_session(test_session_id: str) -> Optional[Dict[str, Any]]:
    with _read_connection() as conn:
        row = conn.execute(
            "SELECT * FROM acvp_requests WHERE test_session_id = ?",
            (test_session_id,),
        ).fetchone()
    return _row_to_acvp_request(row) if row is not None else None


def save_acvp_request(request: Dict[str, Any]) -> None:
    with _write_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE acvp_requests
            SET status = ?, certification_json = ?, message = ?, approved_url = ?,
                updated_at = ?
            WHERE request_id = ?
            """,
            (
                request["status"],
                json_dumps(request["certification"]),
                request.get("message"),
                request.get("approvedUrl"),
                request.get("updatedAt") or utc_now_iso(),
                request["requestId"],
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(request["requestId"])


def record_state_event(
    entity_type: str,
    entity_id: str,
    from_status: Optional[str],
    to_status: Optional[str],
    event: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    with _write_connection() as conn:
        conn.execute(
            """
            INSERT INTO state_events (
                entity_type, entity_id, from_status, to_status, event,
                details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                from_status,
                to_status,
                event,
                _json_or_none(details),
                utc_now_iso(),
            ),
        )


def list_state_events(entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
    with _read_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM state_events
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY id
            """,
            (entity_type, entity_id),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "entityType": row["entity_type"],
            "entityId": row["entity_id"],
            "fromStatus": row["from_status"],
            "toStatus": row["to_status"],
            "event": row["event"],
            "details": json_loads(row["details_json"], default=None),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


class StoreProxy(MutableMapping[str, Dict[str, Any]]):
    def __init__(
        self,
        *,
        key_name: str,
        get_fn: Callable[[str], Optional[Dict[str, Any]]],
        list_fn: Callable[[], List[Dict[str, Any]]],
        save_fn: Callable[[Dict[str, Any]], None],
        delete_fn: Callable[[str], bool],
        clear_fn: Callable[[], None],
    ):
        self._key_name = key_name
        self._get_fn = get_fn
        self._list_fn = list_fn
        self._save_fn = save_fn
        self._delete_fn = delete_fn
        self._clear_fn = clear_fn

    def __getitem__(self, key: str) -> Dict[str, Any]:
        value = self._get_fn(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        record = dict(value)
        record.setdefault(self._key_name, key)
        self._save_fn(record)

    def __delitem__(self, key: str) -> None:
        if not self._delete_fn(key):
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        for item in self._list_fn():
            yield str(item[self._key_name])

    def __len__(self) -> int:
        return len(self._list_fn())

    def get(self, key: str, default: Any = None) -> Any:
        value = self._get_fn(key)
        return default if value is None else value

    def clear(self) -> None:
        self._clear_fn()

    def values(self):  # type: ignore[override]
        return self._list_fn()

    def items(self):  # type: ignore[override]
        return [(item[self._key_name], item) for item in self._list_fn()]


ACVP_SKELETON_SESSION_STORE = StoreProxy(
    key_name="testSessionId",
    get_fn=get_acvp_session,
    list_fn=lambda: list_acvp_sessions(),
    save_fn=save_acvp_session,
    delete_fn=delete_acvp_session,
    clear_fn=clear_acvp_sessions,
)

ACVP_SKELETON_VECTOR_SET_STORE = StoreProxy(
    key_name="vectorSetId",
    get_fn=get_acvp_vector_set,
    list_fn=lambda: _list_all_acvp_vector_sets(),
    save_fn=save_acvp_vector_set,
    delete_fn=delete_acvp_vector_set,
    clear_fn=clear_acvp_vector_sets,
)


_ACVP_SESSION_CORE_KEYS = {
    "testSessionId",
    "label",
    "status",
    "vectorSetIds",
    "registration",
    "negotiatedCapabilities",
    "productionReady",
    "profile",
    "demoOnly",
    "notProductionAcvp",
    "createdAt",
    "updatedAt",
    "expiresAt",
}

_ACVP_VECTOR_SET_CORE_KEYS = {
    "vectorSetId",
    "vsId",
    "testSessionId",
    "status",
    "algorithm",
    "mode",
    "revision",
    "prompt",
    "expectedResults",
    "response",
    "validationResult",
    "report",
    "downloadedAt",
    "submittedAt",
    "validatedAt",
    "createdAt",
    "updatedAt",
}


def _list_all_acvp_vector_sets() -> List[Dict[str, Any]]:
    with _read_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM acvp_vector_sets ORDER BY created_at, vector_set_id"
        ).fetchall()
        report_stores = {
            row["vector_set_id"]: _load_acvp_report_store(
                conn,
                row["vector_set_id"],
            )
            for row in rows
        }
    return [
        _row_to_acvp_vector_set(
            row,
            report_store=report_stores[row["vector_set_id"]],
        )
        for row in rows
    ]


def _row_to_acvp_session(row: Dict[str, Any]) -> Dict[str, Any]:
    extra = json_loads(row["extra_json"], default={}) or {}
    vector_set_ids = json_loads(row["vector_set_ids_json"], default=[]) or []
    session = dict(extra)
    session.update(
        {
            "testSessionId": row["test_session_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "status": row["status"],
            "label": row["label"],
            "expiresAt": row["expires_at"],
            "vectorSetIds": vector_set_ids,
            "productionReady": bool(row["production_ready"]),
            "profile": row["profile"],
            "demoOnly": bool(row["demo_only"]),
            "notProductionAcvp": bool(row["not_production_acvp"]),
        }
    )
    registration = json_loads(row["registration_json"], default=None)
    if registration is not None:
        session["registration"] = registration
    negotiated = json_loads(row["negotiated_capabilities_json"], default=None)
    if negotiated is not None:
        session["negotiatedCapabilities"] = negotiated
    session.setdefault(
        "vectorSetUrls",
        [f"/acvp/v1/vectorSets/{vector_set_id}" for vector_set_id in vector_set_ids],
    )
    session.setdefault("stateHistory", [])
    return session


def _row_to_acvp_vector_set(
    row: Dict[str, Any],
    *,
    report_store: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    extra = json_loads(row["extra_json"], default={}) or {}
    vector_set = dict(extra)
    vector_set.update(
        {
            "vectorSetId": row["vector_set_id"],
            "vsId": row["vs_id"],
            "testSessionId": row["test_session_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "status": row["status"],
            "prompt": json_loads(row["prompt_json"]),
            "expectedResults": json_loads(row["expected_results_json"], default=None),
            "response": json_loads(row["response_json"], default=None),
            "validationResult": json_loads(row["validation_result_json"], default=None),
            "report": report_store,
            "mode": row["mode"],
            "downloadedAt": row["downloaded_at"],
            "submittedAt": row["submitted_at"],
            "validatedAt": row["validated_at"],
            "productionReady": False,
            "profile": "local-fips204-skeleton",
            "demoOnly": True,
            "notProductionAcvp": True,
        }
    )
    vector_set.setdefault("stateHistory", [])
    return vector_set


def _row_to_acvp_request(row: Dict[str, Any]) -> Dict[str, Any]:
    request = {
        "requestId": int(row["request_id"]),
        "testSessionId": row["test_session_id"],
        "url": f"/acvp/v1/requests/{int(row['request_id'])}",
        "status": row["status"],
        "certification": json_loads(row["certification_json"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if row["message"] is not None:
        request["message"] = row["message"]
    if row["approved_url"] is not None:
        request["approvedUrl"] = row["approved_url"]
    return request


def _safe_prompt_summary(prompt: Any) -> Dict[str, Any]:
    try:
        return summarize_vector_set(normalize_acvp_json(prompt))
    except (AcvpParseError, AttributeError, TypeError):
        return {}


def _public_vs_id(
    vector_set: Dict[str, Any],
    *,
    summary: Optional[Dict[str, Any]] = None,
) -> int:
    value = vector_set.get("vsId")
    if value is None:
        value = (summary or _safe_prompt_summary(vector_set.get("prompt"))).get("vsId")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Vector set requires a non-negative numeric vsId")
    prompt_vs_id = (summary or _safe_prompt_summary(vector_set.get("prompt"))).get("vsId")
    if prompt_vs_id is not None and prompt_vs_id != value:
        raise ValueError("Vector set vsId must match prompt.vsId")
    return value


def _migrate_public_vs_ids(conn: _ConnectionAdapter) -> None:
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

    if "vs_id" not in columns:
        conn.execute(
            "ALTER TABLE acvp_vector_sets ADD COLUMN vs_id INTEGER"
        )

    rows = conn.execute(
        """
        SELECT vector_set_id, test_session_id, vs_id, prompt_json, extra_json
        FROM acvp_vector_sets
        WHERE vs_id IS NULL
        """
    ).fetchall()

    for row in rows:
        prompt = json_loads(row["prompt_json"], default=None)
        extra = json_loads(row["extra_json"], default={}) or {}
        summary = _safe_prompt_summary(prompt)
        value = summary.get("vsId")

        if value is None:
            value = extra.get("vsId")

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError(
                "Cannot migrate ACVP vector record without a valid numeric vsId: "
                f"{row['vector_set_id']}"
            )

        conn.execute(
            "UPDATE acvp_vector_sets SET vs_id = ? WHERE vector_set_id = ?",
            (value, row["vector_set_id"]),
        )

    try:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_acvp_vector_sets_session_vs_id
            ON acvp_vector_sets(test_session_id, vs_id)
            """
        )
    except psycopg.IntegrityError as exc:
        raise RuntimeError(
            "Cannot migrate duplicate numeric vsId values within an ACVP test session"
        ) from exc

def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json_dumps(value)


def _extra_fields(record: Dict[str, Any], core_keys: set[str]) -> Dict[str, Any]:
    return {key: value for key, value in record.items() if key not in core_keys}


class _ConnectionContext:
    def __init__(self, *, write: bool):
        self._write = write
        self._conn: Optional[_ConnectionAdapter] = None

    def __enter__(self) -> _ConnectionAdapter:
        self._conn = connect()
        return self._conn

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        assert self._conn is not None
        try:
            if self._write and exc_type is None:
                self._conn.commit()
            elif self._write:
                self._conn.rollback()
        finally:
            self._conn.close()


def _read_connection() -> _ConnectionContext:
    return _ConnectionContext(write=False)


def _write_connection() -> _ConnectionContext:
    return _ConnectionContext(write=True)
