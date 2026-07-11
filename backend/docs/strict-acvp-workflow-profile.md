# Strict ACVP Workflow Profile

Phase 5-4 adds a workflow profile switch for `/acvp/v1` so local skeleton
behavior stays available while strict responses can move closer to ACVP protocol
shape.

This is not a production ACVP server. It is a local skeleton with a stricter
route/response profile.

## Profiles

`generationProfile` and `workflowProfile` are separate controls:

| Control | Values | Purpose |
| --- | --- | --- |
| `generationProfile` | `local-debug`, `nist-conformance` | Controls generated vector counts and local KAT coverage. |
| `workflowProfile` | `local`, `strict` | Controls `/acvp/v1` route behavior, response shape, and local metadata isolation. |

The default workflow profile is `local`. Strict behavior can be enabled per
request:

```text
?workflowProfile=strict
```

The environment variable `ACVP_WORKFLOW_PROFILE=strict` can make strict the
default for future deployments. Invalid values return `400 INVALID_WORKFLOW_PROFILE`.

## Local vs Strict

| Area | local | strict |
| --- | --- | --- |
| Vector set GET | Local wrapper containing `prompt` and state metadata. | ACVP algorithm payload directly. |
| `isSample` default | `true` | `false` |
| Expected endpoint | Local `{expectedResults: ...}` wrapper. | Direct expected payload only for sample vector sets. |
| Non-sample expected | Downloadable in local skeleton. | `403 EXPECTED_RESULTS_NOT_AVAILABLE_FOR_NON_SAMPLE`. |
| POST/PUT results success | Returns local validation/results body. | `204 No Content`; use GET results for disposition. |
| GET vectorSet results | Local wrapper plus diagnostics. | Direct ACVP-style `results` object. |
| GET testSession results | Local diagnostic summary/report shape. | Protocol-style `{passed, results}` summary. |
| Flat vectorSet aliases | Enabled. | `404 LOCAL_COMPATIBILITY_ALIAS_DISABLED`. |
| Local helper routes | Enabled. | `409 LOCAL_HELPER_ROUTE_DISABLED`. |
| Paging links | Keeps local `previous`. | Uses `prev`; no `previous`. |

## Strict Shapes

Strict vector set download returns the vector set itself:

```json
[
  {"acvVersion": "1.0"},
  {
    "vsId": 1,
    "algorithm": "ML-DSA",
    "mode": "keyGen",
    "revision": "FIPS204",
    "isSample": false,
    "testGroups": []
  }
]
```

Strict expected results are sample-only. Sample vector sets return the expected
payload directly. Non-sample vector sets keep expectedResults stored internally
for server-side validation, but the `/expected` route returns 403.

Strict successful result submission returns 204:

```text
POST /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results
PUT  /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results
```

Malformed response schema still returns 400. A cryptographically wrong but
well-formed response is accepted at HTTP level and later appears as `fail` from
GET results.

Strict vector set results return the existing disposition adapter shape:

```json
[
  {"acvVersion": "1.0"},
  {
    "results": {
      "vsId": 1,
      "disposition": "passed",
      "tests": [{"tcId": 1, "result": "passed", "reason": ""}]
    }
  }
]
```

`showExpected=false` is the default and does not expose expected/provided values.
`showExpected=true` is allowed for strict sample vector sets and rejected for
strict non-sample vector sets with
`403 SHOW_EXPECTED_NOT_AVAILABLE_FOR_NON_SAMPLE`.

Strict test session results return a protocol-style summary:

```json
[
  {"acvVersion": "1.0"},
  {
    "passed": true,
    "results": [
      {
        "vectorSetUrl": "/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}",
        "status": "passed",
        "disposition": "passed"
      }
    ]
  }
]
```

## Local-Only Routes

Strict disables flat compatibility aliases:

```text
/acvp/v1/vectorSets/{vectorSetId}
/acvp/v1/vectorSets/{vectorSetId}/expectedResults
/acvp/v1/vectorSets/{vectorSetId}/results
```

Strict also disables local helper routes:

```text
/acvp/v1/testSessions/{sessionId}/vectorSets/generate
/acvp/v1/testSessions/{sessionId}/submit
```

Use `workflowProfile=local` for those local skeleton flows.

## Remaining Gaps

- Auth/JWT/mTLS is not implemented.
- Large submission and async validation are not implemented.
- Vendor/module/OE/dependency resources are not implemented.
- Full ACVP query parser is not implemented.
- FIPS203 / ML-KEM backend is not merged.
- The validator is still a local expected-vs-response comparator using stored
  expectedResults, not a production hidden validation service.
- Strict workflow profile is protocol-shape hardening, not full production ACVP
  compliance.

## Tests

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate

ACVP_DB_PATH=/tmp/acvp_phase54_test.sqlite3 pytest -q tests/conformance/test_acvp_strict_workflow_profile.py
ACVP_DB_PATH=/tmp/acvp_phase54_test.sqlite3 pytest -q tests/conformance/test_acvp_strict_expected_results.py
ACVP_DB_PATH=/tmp/acvp_phase54_test.sqlite3 pytest -q tests/conformance/test_acvp_strict_results_submission.py
ACVP_DB_PATH=/tmp/acvp_phase54_test.sqlite3 pytest -q tests/conformance/test_acvp_strict_response_shapes.py
ACVP_DB_PATH=/tmp/acvp_phase54_conformance.sqlite3 pytest -q tests/conformance
ACVP_DB_PATH=/tmp/acvp_phase54_full.sqlite3 pytest -q
```
