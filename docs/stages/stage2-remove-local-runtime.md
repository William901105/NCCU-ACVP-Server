# Stage 2: Remove Local Runtime

> Historical Stage 2 implementation record. It is not a current setup or API
> guide. See the [documentation index](../README.md).

## Scope

Stage 2 removes the local ML-DSA execution path from production code. The
application has one public workflow:

```text
registration -> NIST GenVal prompt -> external IUT response -> NIST GenVal results
```

`POST /acvp/v1/testSessions` accepts registration containers only. Prompt
creation remains a policy error (`STRICT_REGISTRATION_REQUIRED`), and
`autoGenerateExpectedResults` remains rejected with
`AUTO_EXPECTED_RESULTS_NOT_SUPPORTED`.

## Runtime Contract

- Public endpoints are `/acvp/v1/*` plus `/api/health`.
- NIST GenVal is the only generator and validator. Configuration, execution,
  or artifact failures return NIST GenVal error codes and never use a fallback.
- Generated prompt, expected results, and internal projection are stored as
  separate artifacts. The internal projection is never exposed; expected
  results are available only when `isSample` is true.
- The application no longer registers import, validation, report, sample-data,
  or demo routes.
- The ML-DSA provider implements registration validation, capability
  negotiation, prompt validation, and response validation only. It does not
  expose vector generation, expected-result generation, or result validation.

Removed endpoint families are `/api/oracle/mldsa/*`, `/api/import*`,
`/api/validate`, `/api/report/*`, `/api/demo/*`, `/api/load-sample`, and
`/api/sample-data`; these paths now return HTTP 404.

## Removed Components

The local oracle package, local expected-result generator, local vector
generator, validator, reports, sample loader, import persistence helpers,
demo-session helpers, and their dedicated tests were deleted. The frontend now
contains only the strict registration, vector-set, IUT-response, and NIST-result
views.

The SQLite schema is not migrated or destructively changed. Existing
`imports` and `demo_sessions` tables remain for compatibility, but production
runtime code neither reads nor writes them.

`IUT-tests/mldsa-native/` remains the external implementation-under-test
harness. The sample and NIST fixtures remain available to tests but are not
served by production routes.

## Evidence

`docs/baseline/openapi-stage2-strict.json` is generated from the running
application's OpenAPI schema. Stage 0 and Stage 1 snapshots remain unchanged.
Focused Stage 2 tests cover removed endpoints, OpenAPI surface, all ML-DSA
modes, NIST pass/fail results, missing projections, and the no-fallback error
path. Backend verification reports `50 passed`; the frontend TypeScript/Vite
production build also passes. Stage 3 can build on this strict-only runtime
without restoring local execution paths.
