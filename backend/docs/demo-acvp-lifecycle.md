# Local ACVP-Like Demo Lifecycle

Phase 2-9 added a demo lifecycle under `/api/demo/acvp`. Phase 4-1 persists
that local lifecycle in SQLite.

This is explicitly a local demo. It is not a production ACVP server and does
not implement the official ACVP `/acvp/v1/testSessions` protocol. Responses
include `demoOnly: true` and `notProductionAcvp: true` to keep that boundary
visible.

No JWT, TLS/auth, production ACVP registration negotiation, metadata submission,
certificate workflow, frontend change, or `mldsa-native` change is included in
this phase.

## Endpoints

```text
POST   /api/demo/acvp/test-sessions
GET    /api/demo/acvp/test-sessions
GET    /api/demo/acvp/test-sessions/{sessionId}
GET    /api/demo/acvp/test-sessions/{sessionId}/vector-set
POST   /api/demo/acvp/test-sessions/{sessionId}/responses
GET    /api/demo/acvp/test-sessions/{sessionId}/validation
GET    /api/demo/acvp/test-sessions/{sessionId}/report
DELETE /api/demo/acvp/test-sessions/{sessionId}
```

## Create Session

```json
{
  "prompt": {},
  "label": "optional label",
  "autoGenerateExpectedResults": true
}
```

The backend validates the prompt. When `autoGenerateExpectedResults` is true,
it generates expectedResults and validates the generated response schema.

The create response is a metadata summary and does not include full vector set
material. Use the session detail or vector-set endpoint when full prompt or
expectedResults data is needed.

## Submit Response

```json
{
  "response": {},
  "validateImmediately": true
}
```

The backend validates the response schema against the prompt mode, stores it in
the SQLite-backed session, and optionally runs validation immediately.

Matching responses return status `validated`. Responses with failed, missing,
malformed, or extra cases return status `failed` with the validation summary.

## Validation And Report

If a response has not been submitted yet:

```text
GET /validation -> 409
GET /report     -> 409
```

After response submission, validation and report endpoints run validation on
demand if needed. The report reuses the existing local report builder and uses
the `sessionId` as the report identifier for this demo lifecycle.

## Session List

The list endpoint returns summaries only:

```json
{
  "sessions": [
    {
      "sessionId": "...",
      "status": "validated",
      "vsId": 1,
      "algorithm": "ML-DSA",
      "mode": "sigGen",
      "revision": "FIPS204",
      "testGroupCount": 1,
      "testCaseCount": 1,
      "demoOnly": true,
      "notProductionAcvp": true
    }
  ]
}
```

It does not include full prompt, secret key, signatures, expectedResults, or
submitted response data.

## Manual Check

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate
ACVP_DB_PATH=/tmp/acvp_phase41_manual.sqlite3 \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Create a session:

```bash
curl -s -X POST http://127.0.0.1:8000/api/demo/acvp/test-sessions \
  -H "Content-Type: application/json" \
  -d @/tmp/demo-session-create.json
```

Submit a response:

```bash
curl -s -X POST http://127.0.0.1:8000/api/demo/acvp/test-sessions/$SESSION_ID/responses \
  -H "Content-Type: application/json" \
  -d @/tmp/demo-session-response.json
```

Fetch the report:

```bash
curl -s http://127.0.0.1:8000/api/demo/acvp/test-sessions/$SESSION_ID/report
```
