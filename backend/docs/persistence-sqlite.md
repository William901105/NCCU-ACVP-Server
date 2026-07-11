# SQLite Persistence

Phase 4-1 adds durable local SQLite persistence for the ML-DSA demo and `/acvp/v1` skeleton lifecycle. This phase does not make the server production-ready and does not add authentication, mTLS, PostgreSQL, async validation, Docker, or vendor/module/OE/dependency CRUD.

## DB Path

Default path:

```text
backend/data/acvp.sqlite3
```

Override with:

```bash
ACVP_DB_PATH=/tmp/acvp_phase41_test.sqlite3
```

The parent directory is created automatically. The backend initializes the schema during FastAPI lifespan startup and repository calls also initialize lazily for direct test/service usage.

## Tables

```text
imports
demo_sessions
acvp_sessions
acvp_vector_sets
state_events
```

JSON payload fields are stored as SQLite `TEXT` using `json.dumps` and loaded with `json.loads`. Timestamps are UTC ISO strings. Write operations commit before returning and every repository call opens and closes its SQLite connection.

## Persistent Data

The following local resources now survive server restart when the same DB path is reused:

- `/api/import` and generated/imported bundles
- `/api/validate` validation results
- `/api/report` reports
- `/api/demo/acvp/test-sessions` demo sessions, responses, validation, and reports
- `/acvp/v1/testSessions` skeleton sessions
- `/acvp/v1/vectorSets` skeleton vector sets
- vector set response submissions
- vector set validation results and reports
- local state transitions in `state_events`

## Not Production Ready

Phase 4-1 still intentionally excludes:

- JWT/login/refresh token
- mTLS
- PostgreSQL or production database deployment
- async validation
- vendor/module/OE/dependency CRUD
- production ACVP interoperability guarantees

All `/acvp/v1` responses continue to include:

```json
{
  "productionReady": false,
  "profile": "local-fips204-skeleton",
  "demoOnly": true,
  "notProductionAcvp": true
}
```

## Tests

Run the backend tests with a temporary DB:

```bash
cd NCCU-ACVP-Server/backend
ACVP_DB_PATH=/tmp/acvp_phase41_test.sqlite3 .venv/bin/pytest -q
```

## Manual Restart Check

Start the backend with an explicit DB:

```bash
cd NCCU-ACVP-Server/backend
ACVP_DB_PATH=/tmp/acvp_phase41_manual.sqlite3 \
  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Create a local skeleton session, submit matching expected results, stop uvicorn, restart it with the same `ACVP_DB_PATH`, then verify:

```text
GET /acvp/v1/testSessions/{sessionId}
GET /acvp/v1/vectorSets/{vectorSetId}/results
GET /api/import/{importId}
GET /api/report/{importId}
```

The records should still be available after restart.
