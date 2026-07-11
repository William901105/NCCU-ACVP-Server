from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, MutableMapping, Optional

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
    FOREIGN KEY(test_session_id) REFERENCES acvp_sessions(test_session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX IF NOT EXISTS idx_state_events_entity ON state_events(entity_type, entity_id);
"""


def get_db_path() -> Path:
    configured = os.environ.get("ACVP_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / "data" / "acvp.sqlite3"


def init_db() -> None:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def reset_db_for_tests() -> None:
    path = get_db_path()
    if path.exists():
        path.unlink()
    init_db()


def connect() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
        sql += " LIMIT -1 OFFSET ?"
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


def save_acvp_vector_set(vector_set: Dict[str, Any]) -> None:
    now = utc_now_iso()
    prompt = vector_set["prompt"]
    expected_results = vector_set.get("expectedResults")
    summary = _safe_prompt_summary(prompt)
    created_at = vector_set.get("createdAt") or now
    updated_at = vector_set.get("updatedAt") or now
    extra = _extra_fields(vector_set, _ACVP_VECTOR_SET_CORE_KEYS)
    values = (
        vector_set["testSessionId"],
        vector_set["status"],
        summary.get("algorithm"),
        vector_set.get("mode") or summary.get("mode"),
        summary.get("revision"),
        json_dumps(prompt),
        json_dumps(expected_results),
        _json_or_none(vector_set.get("response")),
        _json_or_none(vector_set.get("validationResult")),
        _json_or_none(vector_set.get("report")),
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
            SET test_session_id = ?, status = ?, algorithm = ?, mode = ?,
                revision = ?, prompt_json = ?, expected_results_json = ?,
                response_json = ?, validation_result_json = ?, report_json = ?,
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
                    vector_set_id, test_session_id, status, algorithm, mode, revision,
                    prompt_json, expected_results_json, response_json,
                    validation_result_json, report_json, downloaded_at, submitted_at,
                    validated_at, created_at, updated_at, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (vector_set["vectorSetId"], *values),
            )


def get_acvp_vector_set(vector_set_id: str) -> Optional[Dict[str, Any]]:
    with _read_connection() as conn:
        row = conn.execute(
            "SELECT * FROM acvp_vector_sets WHERE vector_set_id = ?",
            (vector_set_id,),
        ).fetchone()
    return _row_to_acvp_vector_set(row) if row is not None else None


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
    return [_row_to_acvp_vector_set(row) for row in rows]


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
    return [_row_to_acvp_vector_set(row) for row in rows]


def _row_to_acvp_session(row: sqlite3.Row) -> Dict[str, Any]:
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


def _row_to_acvp_vector_set(row: sqlite3.Row) -> Dict[str, Any]:
    extra = json_loads(row["extra_json"], default={}) or {}
    vector_set = dict(extra)
    vector_set.update(
        {
            "vectorSetId": row["vector_set_id"],
            "testSessionId": row["test_session_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "status": row["status"],
            "prompt": json_loads(row["prompt_json"]),
            "expectedResults": json_loads(row["expected_results_json"], default=None),
            "response": json_loads(row["response_json"], default=None),
            "validationResult": json_loads(row["validation_result_json"], default=None),
            "report": json_loads(row["report_json"], default=None),
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


def _safe_prompt_summary(prompt: Any) -> Dict[str, Any]:
    try:
        return summarize_vector_set(normalize_acvp_json(prompt))
    except (AcvpParseError, AttributeError, TypeError):
        return {}


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json_dumps(value)


def _extra_fields(record: Dict[str, Any], core_keys: set[str]) -> Dict[str, Any]:
    return {key: value for key, value in record.items() if key not in core_keys}


class _ConnectionContext:
    def __init__(self, *, write: bool):
        self._write = write
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Connection:
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
