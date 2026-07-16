# Stage 7 - NIST Priority-0 Protocol Interoperability

Stage 7 starts from merged strict commit
`cc581adf4e0ea986ac92f5850afc8b75515b3339`. The tested implementation and
acceptance-test freeze is `bbcddee7d798604c4229f960742e67d80157bb77`.
This stage remediates only Stage 6 findings F-01, F-02, and F-03. It is not a
claim of complete ACVP conformance or NIST/CAVP certification.

## Official References

- Rendered ML-KEM draft: `draft-celi-acvp-ml-kem-01`, published 2026-04-16,
  expiring 2026-10-18:
  <https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html#name>
- Official protocol source: <https://github.com/usnistgov/ACVP>
- Protocol source and current default-branch commit:
  `178fe4085b0bffc4f8b94433c965229623dc3bc7`
- Stage 6 used the same official commit. Priority-0 envelope, vector identity,
  certification PUT, and request-resource definitions did not change.
- Vendored NIST ACVP-Server GenVal source commit:
  `15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0`

The implementation follows the official protocol source in
`src/protocol/sections/11-messaging.adoc` and the ML-KEM top-level numeric
`vsId` definition. The rendered draft and repository source did not conflict.

## F-02 Registration Envelope

Before Stage 7, the server accepted only a bare registration object. The
canonical request is now:

```json
[
  {"acvVersion": "1.0"},
  {
    "algorithms": [{
      "algorithm": "ML-KEM",
      "mode": "keyGen",
      "revision": "FIPS203",
      "parameterSets": ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
    }],
    "isSample": true
  }
]
```

An algorithm-neutral parser requires exactly a version object and body object,
supports only `acvVersion` 1.0, and returns structured enveloped errors. The
same parser handles canonical result submissions. Bare registration objects
remain accepted only as deprecated local compatibility and receive
`Deprecation` and `Warning` headers; they still pass the same strict
registration schema.

## F-03 Public Numeric vsId

SQLite retains `vector_set_id TEXT` as the internal primary key and artifact
key. The additive migration adds `vs_id INTEGER`, backfills it from prompt JSON
or legacy extra JSON, and creates `UNIQUE(test_session_id, vs_id)`. Invalid or
duplicate legacy data stops migration with an explicit error; initialization
is idempotent and does not drop data.

Canonical vector URLs, session `vsIds`, the numeric compatibility alias
`vectorSetIds`, prompts, expected results, responses, validation results, and
session results all use the same numeric `vsId`. Public nested lookup is scoped
by test-session ID plus `vsId`. Public serializers remove old internal vector
IDs from state-event metadata.

Hidden legacy UUID routes issue a 308 redirect with `Deprecation`, `Warning`,
and canonical `Link` headers. Unknown and cross-session UUIDs return a sanitized
404. The UUID catch-all routes are excluded from OpenAPI and declared after the
integer canonical routes. Direct Python handler calls retain a non-HTTP legacy
projection solely for historical conformance tests.

## F-01 Certification Requests

`PUT /acvp/v1/testSessions/{testSessionId}` accepts the official envelope and
URL-reference form:

```json
[
  {"acvVersion": "1.0"},
  {
    "moduleUrl": "/acvp/v1/modules/20",
    "oeUrl": "/acvp/v1/oes/60",
    "algorithmPrerequisites": []
  }
]
```

The module and OE references are validated as opaque ACVP resource identifiers
because this repository has no metadata-authority service. Optional algorithm
prerequisites follow the official nested algorithm/validation-ID shape.

Certification is accepted only when vector sets exist, all results were
submitted, every NIST GenVal result passed, the derived session `passed` and
`publishable` values are true, and the session is neither cancelled nor
expired. The standard flow does not require local `/submit`.

Accepted certification creates one persistent `acvp_requests` row per session.
`GET /acvp/v1/requests/{requestId}` returns the stable official request shape.
Identical PUT requests are idempotent; a different payload conflicts. A pending
request becomes `rejected` if its session is later cancelled or expires.

This server has no external validation authority, so requests remain truthful
in official `initial` status with an explanatory message. It never creates an
`approvedUrl`, certificate, or validation ID. Local
`POST /testSessions/{id}/submit` remains a deprecated local aggregate-finalize
extension and does not create a certification request.

## Verification

- Stage 4 focused: 6 passed.
- Stage 5 focused: 96 passed.
- Stage 6 deterministic/provider: 16 passed.
- Stage 7 focused: 30 passed.
- Full backend: 205 passed, 4 skipped.
- Live NIST normal: 3 passed, 1 skipped.
- Live NIST unavailable: 1 passed, 3 deselected.
- Frontend production build: passed, 34 modules transformed.
- Orleans was stopped after the unavailable gate.

Detailed commands and durations are recorded under `tests/evidence/stage7/`.

## Deferred Findings

F-04 complete test-session projection, F-05 algorithm discovery projection,
F-06 paging shape, F-07 `showExpected`, F-08 the existing results-route OpenAPI
mismatch, and F-09 general documentation cleanup remain deferred. Stage 7 also
does not add a metadata authority, frontend FIPS 203 workflow, real ML-KEM IUT,
local oracle or fallback, mixed ML-DSA/ML-KEM sessions, or certificate issuance.
