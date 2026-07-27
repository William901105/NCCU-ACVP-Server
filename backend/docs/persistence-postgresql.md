# PostgreSQL Persistence

The NCCU ACVP Server now uses PostgreSQL as its only storage backend.
SQLite support and the runtime storage fallback have been removed.

## Required Configuration

The backend requires either `DATABASE_URL` or `ACVP_DATABASE_URL`.

Example:

~~~text
postgresql://acvp_app:<password>@127.0.0.1:5432/acvp
~~~

Use separate databases:

~~~text
acvp       Application database
acvp_test  Dedicated automated test database
~~~

Automated tests must never use the `acvp` database. The test reset function
refuses to operate unless the configured database name matches `acvp_test`.

## Tables

~~~text
imports
demo_sessions
acvp_sessions
acvp_vector_sets
acvp_requests
state_events
~~~

Report artifact history is currently stored in
`acvp_vector_sets.report_json`.

## Persistent Data

PostgreSQL persists:

- imported and generated validation bundles
- demo sessions and reports
- ACVP test sessions and vector sets
- submitted IUT responses
- validation results and report history
- certification requests
- state transition history

## Application Startup

~~~powershell
$env:DATABASE_URL = "postgresql://acvp_app:<password>@127.0.0.1:5432/acvp"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
~~~

## Automated Tests

~~~powershell
$env:ACVP_TEST_DATABASE_URL = "postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test"
python -m pytest backend\tests -q
~~~

## Manual Persistence Check

Start the backend with the `acvp` database, complete an ACVP validation,
restart the backend with the same database URL, and query the previous session,
results, or report.

~~~text
GET /acvp/v1/testSessions/{sessionId}
GET /acvp/v1/testSessions/{sessionId}/vectorSets/{vsId}/reports
~~~

The previously stored records should remain available after restart.
