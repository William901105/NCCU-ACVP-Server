-- Snapshot of backend/app/storage/sqlite_store.py::SCHEMA_SQL at pre-strict baseline.

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
