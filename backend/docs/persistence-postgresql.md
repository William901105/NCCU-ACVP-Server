# PostgreSQL Persistence

The NCCU ACVP Server uses PostgreSQL as its only runtime storage backend.
SQLite runtime support and the implicit local database fallback have been
removed.

## Configuration

Set either `DATABASE_URL` or `ACVP_DATABASE_URL` before starting the backend:

```text
postgresql://acvp_app:<password>@127.0.0.1:5432/acvp
```

`ACVP_SCHEMA_DATABASE_URL` may be set separately when schema ownership and
application data access use different PostgreSQL roles. The backend creates and
migrates its tables during FastAPI lifespan startup.

Automated tests require `ACVP_TEST_DATABASE_URL` and refuse to reset a database
whose name is not `acvp_test` (override the expected name only with
`ACVP_TEST_DATABASE_NAME`). Keep application and test databases separate.

## Tables

```text
imports
demo_sessions
acvp_sessions
acvp_vector_sets
acvp_reports
test_vectors
acvp_requests
state_events
access_tokens
```

`access_tokens` stores only SHA-256 token digests, issue timestamps, expiry
timestamps, and revocation state. The bearer token itself is returned once to
the frontend and stored in browser `localStorage`.

## Access tokens

`POST /acvp/v1/accessTokens` is public and issues an opaque Bearer token. Every
other `/acvp/v1` endpoint requires:

```text
Authorization: Bearer <accessToken>
```

Tokens expire after 30 minutes by default. Configure a value from 60 through
86400 seconds with `ACVP_ACCESS_TOKEN_TTL_SECONDS`. Missing, invalid, revoked,
or expired credentials return HTTP 401 with `WWW-Authenticate: Bearer`.

## Tests

```bash
cd backend
ACVP_TEST_DATABASE_URL=postgresql://acvp_test_user:<password>@127.0.0.1:5432/acvp_test \
  .venv/bin/pytest -q
```

The reset guard is deliberately strict because the test fixture drops and
recreates the ACVP schema for isolation.
