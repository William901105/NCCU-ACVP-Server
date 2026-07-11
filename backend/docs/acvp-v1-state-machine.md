# ACVP v1 Local State Machine

Phase 3-5 adds a formal local state machine for `/acvp/v1` test sessions and vector sets. Phase 4-1 persists that local state machine in SQLite. It is aligned with the NIST ACVP Protocol Specification sections for Test Sessions, Vector Sets, paging/query parameters, and errors where the local skeleton has matching resources. It is not a production ACVP server.

References:

- ACVP Protocol Specification: https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html
- ACVP ML-DSA JSON Specification: https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html
- FIPS 204: https://csrc.nist.gov/pubs/fips/204/final

Every `/acvp/v1` response still includes:

```json
{
  "productionReady": false,
  "profile": "local-fips204-skeleton",
  "demoOnly": true,
  "notProductionAcvp": true
}
```

## Scope

Implemented as local skeleton behavior:

- SQLite-backed testSession/vectorSet lifecycle
- deterministic vector generation from negotiated ML-DSA capabilities
- vector download marking
- vector result submission with synchronous local validation
- session-level submit-for-validation aggregate
- soft cancel for sessions and vector sets
- configurable `expiresInSeconds`
- state history events on sessions and vector sets
- SQLite `state_events` rows for local transition history

Not implemented in this phase:

- production database deployment
- JWT, login, mTLS, or production authorization
- vendor/module/OE/dependency CRUD
- async or large submission processing
- production ACVP interoperability guarantees

## TestSession Statuses

| Status | Meaning |
| --- | --- |
| `created` | Local session record exists but is not ready for vectors/results. |
| `capabilitiesAccepted` | Registration/capabilities were accepted and can generate vector sets. |
| `vectorReady` | One or more vector sets are ready. |
| `vectorDownloaded` | All vector sets were downloaded through `GET /vectorSets/{id}`. |
| `resultsSubmitted` | At least one vector set response has been submitted. |
| `validating` | Local synchronous aggregate validation is in progress. |
| `validated` | All submitted vector sets passed aggregate validation. |
| `failed` | At least one vector set failed aggregate validation. |
| `cancelled` | Session was soft-cancelled. |
| `expired` | Session reached `expiresAt`. |

## VectorSet Statuses

| Status | Meaning |
| --- | --- |
| `created` | Local vector set record exists but expectedResults are not ready. |
| `ready` | Prompt and expectedResults are ready. |
| `downloaded` | Prompt was downloaded through `GET /vectorSets/{id}`. |
| `resultsSubmitted` | A response was submitted. |
| `validating` | Local synchronous vector validation is in progress. |
| `validated` | Response matched expectedResults. |
| `failed` | Response did not match expectedResults. |
| `cancelled` | Vector set was soft-cancelled. |
| `expired` | Vector set reached `expiresAt`. |

## Transition Table

TestSession transitions:

| From | To |
| --- | --- |
| `created` | `capabilitiesAccepted`, `vectorReady`, `cancelled`, `expired` |
| `capabilitiesAccepted` | `vectorReady`, `cancelled`, `expired` |
| `vectorReady` | `vectorDownloaded`, `resultsSubmitted`, `validating`, `validated`, `failed`, `cancelled`, `expired` |
| `vectorDownloaded` | `resultsSubmitted`, `validating`, `validated`, `failed`, `cancelled`, `expired` |
| `resultsSubmitted` | `validating`, `validated`, `failed`, `cancelled`, `expired` |
| `validating` | `resultsSubmitted`, `validated`, `failed`, `cancelled`, `expired` |
| `validated` | `resultsSubmitted`, `validating`, `failed`, `cancelled`, `expired` |
| `failed` | `resultsSubmitted`, `validating`, `validated`, `cancelled`, `expired` |
| `cancelled` | none |
| `expired` | none |

VectorSet transitions:

| From | To |
| --- | --- |
| `created` | `ready`, `cancelled`, `expired` |
| `ready` | `downloaded`, `resultsSubmitted`, `validating`, `validated`, `failed`, `cancelled`, `expired` |
| `downloaded` | `resultsSubmitted`, `validating`, `validated`, `failed`, `cancelled`, `expired` |
| `resultsSubmitted` | `validating`, `validated`, `failed`, `cancelled`, `expired` |
| `validating` | `resultsSubmitted`, `validated`, `failed`, `cancelled`, `expired` |
| `validated` | `resultsSubmitted`, `validating`, `failed`, `cancelled`, `expired` |
| `failed` | `resultsSubmitted`, `validating`, `validated`, `cancelled`, `expired` |
| `cancelled` | none |
| `expired` | none |

Illegal transitions return `409` with a structured skeleton error. `cancelled` and `expired` are terminal for this local skeleton. `validated` and `failed` may still be soft-cancelled, and vector result resubmission is allowed before session-level submit-for-validation finalizes the session.

## State History

Sessions and vector sets include `stateHistory`:

```json
{
  "at": "2026-06-27T00:00:00+00:00",
  "event": "resultsSubmitted",
  "from": "downloaded",
  "to": "resultsSubmitted",
  "reason": "Vector set results submitted.",
  "metadata": {
    "vectorSetId": "uuid"
  }
}
```

Required fields are `at`, `event`, `from`, `to`, and `reason`. Phase 4-1 also writes local transition records to the SQLite `state_events` table. Production systems still need audit retention policy, tamper controls, and operational hardening.

## Endpoints

`POST /acvp/v1/testSessions`

- prompt-based create starts at `created`
- with `autoGenerateExpectedResults=true`, transitions to `vectorReady` and creates a `ready` vector set
- registration create transitions to `capabilitiesAccepted`
- with `autoGenerateVectorSets=true`, transitions to `vectorReady` and creates `ready` vector sets
- optional `expiresInSeconds` sets `expiresAt`

`POST /acvp/v1/testSessions/{sessionId}/vectorSets/generate`

- only `capabilitiesAccepted` sessions can generate
- prompt-based sessions return `409 NEGOTIATED_CAPABILITIES_NOT_AVAILABLE`
- duplicate generation returns `409 VECTOR_SETS_ALREADY_GENERATED`
- cancelled or expired sessions return `409`

`GET /acvp/v1/vectorSets/{vectorSetId}`

- `ready` vector sets transition to `downloaded`
- when all vector sets are downloaded, the session transitions to `vectorDownloaded`
- `validated` and `failed` vector sets remain readable as local skeleton behavior
- cancelled or expired vector sets return `409`

`POST /acvp/v1/vectorSets/{vectorSetId}/results`

- accepted states are `ready`, `downloaded`, `resultsSubmitted`, `validated`, and `failed`
- `created`, `cancelled`, and `expired` return `409`
- local validation is synchronous
- vector flow is `resultsSubmitted -> validating -> validated/failed`
- session aggregate becomes `resultsSubmitted`, `validated`, or `failed`
- after session submit-for-validation, vector result changes return `409 VECTOR_SET_ALREADY_FINALIZED`

`POST /acvp/v1/testSessions/{sessionId}/submit`

- local skeleton endpoint for ACVP Test Session submit-for-validation
- `capabilitiesAccepted` with no vector sets returns `409 VECTOR_SETS_NOT_GENERATED`
- no submissions returns `409 RESULTS_NOT_SUBMITTED`
- incomplete submissions return `409 VECTOR_SET_RESULTS_INCOMPLETE`
- all pass returns session `validated`
- any failed vector set returns session `failed`

`GET /acvp/v1/testSessions/{sessionId}/results`

Returns aggregate summary:

```json
{
  "totalVectorSets": 3,
  "downloadedVectorSets": 3,
  "submittedVectorSets": 3,
  "validatedVectorSets": 2,
  "failedVectorSets": 1,
  "pendingVectorSets": 0,
  "sessionPassed": false
}
```

`DELETE /acvp/v1/testSessions/{sessionId}`

- soft-cancels the session
- non-terminal vector sets are soft-cancelled
- the session remains retrievable

`DELETE /acvp/v1/vectorSets/{vectorSetId}`

- soft-cancels a vector set
- if every vector set in the session is cancelled, the session becomes `cancelled`
- cancelled vector sets cannot accept result submissions

## Expiration

`expiresInSeconds` can be supplied on session create and explicit vector generation. If omitted, no local expiration is set. A value of `0` expires on the next stateful operation.

Stateful endpoints check expiration before changing state:

- `GET /vectorSets/{vectorSetId}`
- `POST /vectorSets/{vectorSetId}/results`
- `GET /vectorSets/{vectorSetId}/expectedResults`
- `POST /testSessions/{sessionId}/vectorSets/generate`
- `POST /testSessions/{sessionId}/submit`
- `DELETE /testSessions/{sessionId}`
- `DELETE /vectorSets/{vectorSetId}`

Expired sessions return `409 TEST_SESSION_EXPIRED`. Expired vector sets return `409 VECTOR_SET_EXPIRED`. There is no background scheduler.

## Paging And Query

`GET /acvp/v1/testSessions?status=vectorReady` supports a simple status filter. Formal paging and query semantics from the ACVP Protocol Specification remain partial and are planned for Phase 4-3.

## Follow-Up Phases

- Phase 4-2: JWT/login/mTLS and authorization boundaries.
- Phase 4-3: paging, query parameters, and production error format hardening.
- Phase 4-4: async validation and large submission handling.

## Manual Validation

Build native oracle:

```bash
cd NCCU-ACVP-Server/backend/native/mldsa_oracle
make clean
make MLDSA_NATIVE_DIR=/root/ACVP204/mldsa-native
```

Run tests:

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate
ACVP_DB_PATH=/tmp/acvp_phase41_test.sqlite3 pytest -q
ACVP_DB_PATH=/tmp/acvp_phase41_test.sqlite3 pytest -q tests/test_acvp_v1_state_machine.py
```

Start backend:

```bash
ACVP_DB_PATH=/tmp/acvp_phase41_manual.sqlite3 \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
