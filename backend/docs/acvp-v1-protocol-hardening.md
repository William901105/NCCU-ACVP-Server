# ACVP v1 Protocol Hardening

This document records Phase 4-3 Commit 1 through Commit 3 protocol hardening:

- Commit 1: NIST canonical nested vector set routes and ACVP array envelope response adaptation.
- Commit 2: vector set results disposition adapter and `showExpected` support.
- Commit 3: paging/query hardening and normalized ACVP error responses.

## Scope

Implemented through Commit 3:

- ACVP array envelope helper for canonical `/acvp/v1` responses.
- Local skeleton metadata under `extensions.localFips204Skeleton`.
- NIST canonical nested vector set routes:
  - `GET /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}`
  - `DELETE /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}`
  - `POST /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results`
  - `PUT /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results`
  - `GET /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results`
  - `GET /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/expected`
- Service helpers for session lookup, vector set lookup, session/vector ownership checks, submit/update, cancel, prompt download, expected retrieval, and result retrieval.
- Flat vector set compatibility aliases retained with `localCompatibilityAlias=true`.
- ACVP-like vector set `results` object for canonical GET/POST/PUT results routes.
- NIST-style ACVP envelope submission body support for vector set results.
- `showExpected` persistence and expected/provided details for failing cases when requested.
- Paged canonical list responses for:
  - `GET /acvp/v1/testSessions?status=<status>&limit=<n>&offset=<n>`
  - `GET /acvp/v1/testSessions/{sessionId}/vectorSets?status=<status>&limit=<n>&offset=<n>`
- Normalized ACVP skeleton errors with `error.code`, `error.message`, `error.path`, `error.requestId`, optional `error.details`, and `X-Request-ID` propagation.

Not implemented in this commit:

- JWT, mTLS, auth, PostgreSQL, async validation, large submission, vendor/module/OE/dependency resources.

## NIST Sources

Protocol authority:

- ACVP Protocol Specification: https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html

ML-DSA JSON authority:

- ACVP ML-DSA JSON Specification: https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html

Documentation index:

- ACVP documentation landing page: https://pages.nist.gov/ACVP/

The usnistgov/ACVP-Server repository is useful implementation/gen-val reference material, but it is not treated as the final authority when it differs from the protocol specification.

## Prompt Versus NIST Check

The Commit 1 task prompt expected nested vector set routes under `testSessions/{sessionId}` and specifically warned that expected result retrieval may be `/expected` instead of `/expectedResults`. The NIST protocol resource hierarchy uses the nested test session/vector set shape and the expected result route name `/expected`; this implementation follows the NIST route names for canonical routes.

The Commit 2 prompt expected a vector set validation result body with a `results` object. The NIST protocol specifies an ACVP envelope whose second object has `results.vsId`, `results.disposition`, and `results.tests`. NIST lists overall dispositions `passed`, `fail`, `unreceived`, `incomplete`, `expired`, `missing`, and `error`. It lists per-test results including `passed`, `fail`, `unreceived`, `incomplete`, `expired`, and `missing`; one nearby example uses `failed`, but this implementation follows the enumerated `fail` value.

NIST also states successful POST result submission may return no content. This local skeleton returns an ACVP envelope with results for developer usability and marks that behavior with `extensions.localFips204Skeleton.localPostReturnsResults=true`. This is a documented local skeleton deviation, not a production-ready claim.

The older local routes under `/acvp/v1/vectorSets/{vectorSetId}` are retained only as local compatibility aliases. They do not override the canonical nested routes.

The Commit 3 prompt requested a `pagination` object. The NIST protocol paging section specifies `totalCount`, `incomplete`, `links`, and `data` for paged responses. This implementation uses those NIST paging fields as the canonical fields and keeps the prompt-style `pagination` object as local skeleton compatibility metadata. The prompt also requested simple `status=<status>` query filters. NIST describes a more general filter syntax using indexed query parameters and operations. This local skeleton supports only `status=<status>` for test session and vector set lists, rejects unknown status values with `400 INVALID_QUERY_PARAMETER`, and documents that limitation.

The NIST error message section describes status-code-driven error behavior and message content, but it does not mandate the exact local object used here. Commit 3 therefore uses a local normalized ACVP skeleton error profile in the ACVP envelope while preserving NIST HTTP status semantics.

## Envelope Policy

Canonical `/acvp/v1` routes return:

```json
[
  {"acvVersion": "1.0"},
  {
    "status": "vectorReady",
    "extensions": {
      "localFips204Skeleton": {
        "productionReady": false,
        "profile": "local-fips204-skeleton",
        "demoOnly": true,
        "notProductionAcvp": true
      }
    }
  }
]
```

The helper functions are:

- `acvp_envelope(body)`
- `acvp_local_metadata()`
- `with_local_metadata(body)`
- `envelope_response(body, include_local_metadata=False)`

The metadata location is intentionally under `extensions.localFips204Skeleton`; canonical protocol body fields no longer carry `productionReady`, `profile`, `demoOnly`, or `notProductionAcvp` at top level. `productionReady` remains `false`.

`/api/...` endpoints are unchanged and are not wrapped with ACVP envelopes.

## Ownership And State

Nested vector set routes enforce that the supplied `vectorSetId` belongs to the supplied `sessionId`.

- Missing session returns `404 UNKNOWN_TEST_SESSION`.
- Missing vector set returns `404 UNKNOWN_VECTOR_SET`.
- Existing vector set under a different session returns `404 UNKNOWN_VECTOR_SET` to avoid leaking existence across sessions.

`DELETE` is a soft cancel. It sets vector set status to `cancelled`, records a `state_events` row, persists the vector set, and cancels the parent session when all vector sets are cancelled.

`PUT .../results` is local skeleton replace behavior. It reuses the same validation and persistence path as POST and marks the response with `localSkeletonPutReplaceBehavior=true`.

## Results Disposition Adapter

Phase 4-3 Commit 2 adds the local results disposition adapter and `showExpected` handling.

Canonical vector set results routes return:

```json
[
  {"acvVersion": "1.0"},
  {
    "results": {
      "vsId": 43201,
      "disposition": "passed",
      "tests": [
        {"tcId": 1, "result": "passed", "reason": ""}
      ]
    },
    "extensions": {
      "localFips204Skeleton": {
        "productionReady": false,
        "profile": "local-fips204-skeleton",
        "demoOnly": true,
        "notProductionAcvp": true
      }
    }
  }
]
```

Canonical `GET /results` no longer returns top-level `validationResult` or `report`. Those local artifacts remain stored in PostgreSQL and may be exposed through local/debug behavior or flat compatibility aliases.

Overall disposition mapping:

| Local condition | ACVP results disposition |
| --- | --- |
| vector set expired | `expired` |
| no validation result and no response | `unreceived` |
| local error recorded in validation result | `error` |
| `summary.failed > 0`, `summary.malformed > 0`, or `summary.extra > 0` | `fail` |
| `summary.missing > 0` | `missing` |
| not all expected tests processed | `incomplete` |
| all expected tests passed | `passed` |
| fallback | `incomplete` |

Per-test result mapping:

| Local validator status | ACVP test result | Reason |
| --- | --- | --- |
| `passed` | `passed` | empty string |
| value mismatch / internal `failed` | `fail` | local validator reason |
| internal `malformed` | `fail` | `response test case is malformed` |
| internal `missing` | `missing` | `response test case is missing` |
| internal `extra` | `fail` | `extra response test case` |
| no response received | `unreceived` | `response not received` |
| not processed | `incomplete` | `test case not processed` |
| expired | `expired` | `vector set expired` |

`showExpected` can be supplied in either the local wrapper body:

```json
{"response": {"vsId": 43201, "testGroups": []}, "showExpected": true}
```

or in a NIST-style ACVP submission envelope:

```json
[
  {"acvVersion": "1.0"},
  {"vsId": 43201, "showExpected": true, "testGroups": []}
]
```

The route removes `showExpected` before ML-DSA response schema validation, stores the boolean on the vector set, and persists the derived `acvpResults` in PostgreSQL. When `showExpected=true`, failing, missing, malformed, and extra test results include `expected` and `provided` objects when available. When `showExpected=false`, those objects are omitted. For keyGen this can expose `sk` in expected/provided data for failing cases; that is local sample/skeleton behavior and should not be treated as production disclosure policy.

## Paging And Query Parameters

Phase 4-3 Commit 3 adds `backend/app/acvp_protocol/paging.py`.

Local policy:

- `limit` defaults to `25`.
- `offset` defaults to `0`.
- `MAX_LIMIT` is `100`.
- `limit` must be an integer from `1` through `100`.
- `offset` must be an integer greater than or equal to `0`.
- Invalid paging or status query values return `400 INVALID_QUERY_PARAMETER`.

`GET /acvp/v1/testSessions` supports:

- `status=<testSessionStatus>`
- `limit=<integer>`
- `offset=<integer>`

`GET /acvp/v1/testSessions/{sessionId}/vectorSets` supports:

- `status=<vectorSetStatus>`
- `limit=<integer>`
- `offset=<integer>`

Paged responses include NIST-style fields:

```json
{
  "totalCount": 100,
  "incomplete": true,
  "links": {
    "first": "/acvp/v1/testSessions?limit=25&offset=0",
    "previous": null,
    "next": "/acvp/v1/testSessions?limit=25&offset=25",
    "last": "/acvp/v1/testSessions?limit=25&offset=75"
  },
  "data": []
}
```

For local skeleton usability, the response also includes the resource-specific alias (`testSessions` or `vectorSetUrls`) and a prompt-style `pagination` object:

```json
{
  "testSessions": [],
  "pagination": {
    "offset": 0,
    "limit": 25,
    "total": 100,
    "returned": 25,
    "incomplete": true
  }
}
```

For vector set listing, the canonical list key is `vectorSetUrls`. The richer local `vectorSets` summary remains present for this skeleton and is also mirrored under `extensions.localFips204Skeleton.vectorSets`.

## Normalized Error Responses

Phase 4-3 Commit 3 adds `backend/app/acvp_protocol/errors.py` and request ID context support.

Canonical `/acvp/v1` errors return an ACVP envelope:

```json
[
  {"acvVersion": "1.0"},
  {
    "error": {
      "code": "INVALID_QUERY_PARAMETER",
      "message": "limit must be an integer between 1 and 100.",
      "path": "$.limit",
      "requestId": "phase43c3-invalid-limit",
      "details": {
        "parameter": "limit",
        "value": "abc"
      }
    },
    "extensions": {
      "localFips204Skeleton": {
        "productionReady": false,
        "profile": "local-fips204-skeleton",
        "demoOnly": true,
        "notProductionAcvp": true
      }
    }
  }
]
```

Behavior:

- `X-Request-ID` is accepted from the client and returned in the response header.
- If no `X-Request-ID` is supplied, the server generates a UUID-like request ID.
- `error.requestId` matches the response header.
- `RequestValidationError`, `HTTPException`, unknown `/acvp/v1` routes, and method-not-allowed responses are normalized for `/acvp/v1`.
- `/api/...` endpoints remain non-ACVP endpoints and are not wrapped in ACVP envelopes.
- Stack traces are not returned in normalized error bodies.

## Remaining Deviations

- Auth/JWT/mTLS remains Phase 4-2.
- Large submission and async validation remain Phase 4-4.
- Vendor/module/OE/dependency resources are out of scope.
- This is still a local skeleton. It is not a production-ready ACVP server.
