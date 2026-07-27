# ACVP v1 Skeleton

Phase 3-2 added a formal `/acvp/v1` namespace as a local skeleton. Phase 3-3 through Phase 3-5 added local ML-DSA capabilities negotiation, deterministic vector generation, and a local test session/vector set state machine. The current PostgreSQL-only storage persists sessions, vector sets, submissions, validation results, reports, requests, and state events.

Phase 4-3 adds protocol hardening:

- NIST canonical nested vector set routes under `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}`.
- ACVP array envelope responses for canonical `/acvp/v1` routes.
- Local skeleton metadata moved under `extensions.localFips204Skeleton`.
- Existing flat vector set routes retained as local compatibility aliases.
- Commit 2 maps internal vector set validation into a NIST-like `results` object and adds `showExpected` support.
- Commit 3 adds local paging/query hardening and normalized ACVP error envelopes with request IDs.

This remains a local skeleton, not a production-ready ACVP server. `/acvp/v1` still reports `productionReady=false`.

References:

- ACVP Protocol Specification: https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html
- ACVP ML-DSA JSON Specification: https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html
- ACVP documentation landing page: https://pages.nist.gov/ACVP/
- FIPS 204: https://csrc.nist.gov/pubs/fips/204/final

## Protocol Authority

The NIST ACVP Protocol Specification is the protocol authority for URI hierarchy, message envelope, workflow, paging, and errors. The NIST ACVP ML-DSA JSON Specification is the algorithm JSON authority. The usnistgov/ACVP-Server repository is useful implementation/gen-val reference material, but it does not override the protocol specification when behavior differs.

For Phase 4-3 Commit 1, the prompt matched the NIST protocol on the important vector set route shape: vector set download, results, update, cancellation, and expected result retrieval are nested below `testSessions/{testSessionId}`. The prompt also correctly called out that the NIST expected result path uses `/expected`, not the old local `/expectedResults` alias.

For Phase 4-3 Commit 2, the implementation follows the NIST result object fields and the enumerated `fail` value. The NIST text also states POST result submission may return no content; this skeleton returns envelope results for developer usability and marks that local behavior in `extensions.localFips204Skeleton`.

For Phase 4-3 Commit 3, the implementation follows NIST paging fields `totalCount`, `incomplete`, `links`, and `data` for paged list bodies. The prompt requested a `pagination` object, so the skeleton also exposes that object as local compatibility metadata. The NIST query parameter section defines a more general indexed filter syntax; this skeleton supports only the documented local `status=<status>` filter on test session and vector set lists.

## ACVP Envelope

Canonical `/acvp/v1` routes now return the ACVP array envelope by default:

```json
[
  {"acvVersion": "1.0"},
  {
    "testSessionId": "uuid",
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

`productionReady`, `profile`, `demoOnly`, and `notProductionAcvp` are no longer top-level fields in canonical protocol bodies. They are placed under `extensions.localFips204Skeleton` so the local skeleton status is visible without polluting the main protocol body.

For debugging, canonical routes accept `profile=debug` or `includeLocalMetadata=true` and may return the older local object shape. `/api/...` routes are not ACVP protocol routes and are not wrapped in the ACVP envelope.

## Endpoints

| Method | Path | Current skeleton behavior |
| --- | --- | --- |
| GET | `/acvp/v1/version` | Returns local skeleton protocol/version metadata in an ACVP envelope. |
| GET | `/acvp/v1/algorithms` | Returns ML-DSA capability summary for the local implementation in an ACVP envelope. |
| GET | `/acvp/v1/testSessions` | Lists PostgreSQL-backed skeleton sessions with `status`, `limit`, and `offset` query hardening. |
| POST | `/acvp/v1/testSessions` | Creates a local prompt-based skeleton session or a registration session that can generate vector sets. |
| GET | `/acvp/v1/testSessions/{sessionId}` | Returns skeleton session detail and vector set metadata. |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets` | Lists vector sets for a skeleton session with `status`, `limit`, and `offset` query hardening. |
| POST | `/acvp/v1/testSessions/{sessionId}/vectorSets/generate` | Local skeleton helper that generates vector sets for a `capabilitiesAccepted` session. |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}` | NIST canonical nested vector set download. Marks `ready` vector sets as `downloaded`. |
| DELETE | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}` | NIST canonical nested vector set cancellation. Soft-cancels the vector set and records state events. |
| POST | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results` | NIST canonical nested result submission. Accepts local wrapper, raw response body, or ACVP array envelope; stores response, `showExpected`, local validation artifacts, and ACVP-style `results`. Returns local envelope results instead of production no-content. |
| PUT | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results` | Local skeleton replace/update behavior for an existing result submission; updates stored `showExpected` and `acvpResults`. |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results` | Returns ACVP envelope with `{"results": {"vsId", "disposition", "tests"}}`; local validationResult/report are not top-level fields. |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/expected` | NIST canonical expected result route name. In this local skeleton it returns generated `expectedResults`; production behavior still requires NIST workflow compliance. |
| GET | `/acvp/v1/testSessions/{sessionId}/results` | Aggregates local vector set results. |
| POST | `/acvp/v1/testSessions/{sessionId}/submit` | Local skeleton session-level submit-for-validation aggregate finalization. |
| DELETE | `/acvp/v1/testSessions/{sessionId}` | Soft-cancels the PostgreSQL-backed skeleton session and non-terminal vector sets. |

## Flat Compatibility Aliases

The older flat vector set routes remain available for local compatibility:

| Method | Path | Alias behavior |
| --- | --- | --- |
| GET | `/acvp/v1/vectorSets/{vectorSetId}` | Calls the same service logic as nested download and returns object shape with `localCompatibilityAlias=true`. |
| DELETE | `/acvp/v1/vectorSets/{vectorSetId}` | Calls the same cancellation logic without session ownership checking and returns `localCompatibilityAlias=true`. |
| POST | `/acvp/v1/vectorSets/{vectorSetId}/results` | Calls the same result submission logic and returns `localCompatibilityAlias=true`. |
| GET | `/acvp/v1/vectorSets/{vectorSetId}/results` | Calls the same result retrieval logic and returns `localCompatibilityAlias=true`. |
| GET | `/acvp/v1/vectorSets/{vectorSetId}/expectedResults` | Local compatibility alias for the old skeleton expectedResults route. |

Flat aliases are not the canonical NIST URI shape. New protocol-facing clients should use the nested `testSessions/{sessionId}/vectorSets/{vectorSetId}` routes.

## Vector Set Results

Canonical vector set results use this shape:

```json
[
  {"acvVersion": "1.0"},
  {
    "results": {
      "vsId": 43201,
      "disposition": "fail",
      "tests": [
        {
          "tcId": 1,
          "result": "fail",
          "reason": "value mismatch"
        }
      ]
    }
  }
]
```

The local skeleton maps internal validator statuses to ACVP results as follows:

| Internal condition | Overall disposition | Per-test result |
| --- | --- | --- |
| all expected tests pass | `passed` | `passed` |
| value mismatch, malformed case, or extra response case | `fail` | `fail` |
| missing response case only | `missing` | `missing` |
| no response received | `unreceived` | `unreceived` |
| expired vector set | `expired` | `expired` |
| not all cases processed | `incomplete` | `incomplete` |
| local adapter/validation error | `error` | `incomplete` |

`showExpected=true` can be supplied in either `{"response": ..., "showExpected": true}` or the second object of an ACVP array envelope. The flag is removed before ML-DSA schema validation, persisted on the vector set, and used for later `GET /results`. When true, non-passing tests include `expected` and `provided` objects where available. When false, those objects are omitted.

The old local `validationResult` and `report` remain persisted for debug/local flows and flat compatibility aliases, but canonical GET results no longer returns them at top level.

## Paging And Query Parameters

Commit 3 supports paging on canonical list endpoints only:

| Endpoint | Supported query parameters |
| --- | --- |
| `GET /acvp/v1/testSessions` | `status`, `limit`, `offset` |
| `GET /acvp/v1/testSessions/{sessionId}/vectorSets` | `status`, `limit`, `offset` |

Paging policy:

- `limit` default: `25`
- `offset` default: `0`
- `limit` maximum: `100`
- invalid `limit`, invalid `offset`, or unknown `status` returns `400 INVALID_QUERY_PARAMETER`

Paged responses include NIST-style `totalCount`, `incomplete`, `links`, and `data`. They also include local skeleton aliases:

- `testSessions` mirrors `data` for session lists.
- `vectorSetUrls` is the canonical vector set URL list.
- `vectorSets` is a local richer summary for skeleton usability.
- `pagination` gives `offset`, `limit`, `total`, `returned`, and `incomplete`.

The `pagination` object and richer `vectorSets` list are local skeleton behavior, not a full production ACVP claim. Local metadata remains under `extensions.localFips204Skeleton`.

## Error Responses

Commit 3 normalizes canonical `/acvp/v1` errors into the ACVP envelope:

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
    }
  }
]
```

The response also carries `X-Request-ID`. If a client supplies `X-Request-ID`, the same value is returned in the header and in `error.requestId`; otherwise a UUID-like value is generated. Unknown `/acvp/v1` routes and method-not-allowed responses are normalized. `/api/...` endpoints remain ordinary local API endpoints and are not wrapped in ACVP envelopes.

## State And Persistence

Nested routes enforce session/vector set ownership. If a vector set does not belong to the supplied session, the local skeleton returns `404 UNKNOWN_VECTOR_SET` to avoid revealing vector set existence across sessions.

`DELETE` performs a soft cancel, not a hard DB row delete. It transitions the vector set to `cancelled`, records a `state_events` row, and cancels the parent session when all vector sets are cancelled. Submitting results to cancelled or expired resources returns stable `409` skeleton errors.

PostgreSQL is the only supported storage backend. Set `DATABASE_URL` or `ACVP_DATABASE_URL` to the `acvp` database connection URL before starting the server.

## Remaining Deviations

- Authentication, JWT, and mTLS remain Phase 4-2.
- Large submission and async validation remain Phase 4-4.
- Vendor/module/OE/dependency resources remain out of scope.
- This skeleton still has local helper routes such as `vectorSets/generate` and `testSessions/{sessionId}/submit`; they are documented as local behavior, not production ACVP claims.
