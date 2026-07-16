# NCCU ACVP Server

NCCU ACVP Server exposes a strict-only ACVP v1 workflow for FIPS 203 / ML-KEM
and FIPS 204 / ML-DSA.

## Algorithm-neutral Core

The strict runtime is assembled from algorithm-neutral protocol services and
an injected algorithm module registry. Each module owns its immutable
descriptor, schema validation, capability negotiation, NIST registration
mapping, and NIST validation normalization. The protocol layer dispatches by
`AlgorithmIdentity` and does not import concrete algorithm packages.

`GET /acvp/v1/algorithms` is generated entirely from registered descriptors.
ML-DSA and ML-KEM are registered once during application startup with provider
IDs `nist-ml-dsa-fips204` and `nist-ml-kem-fips203`. The backend can dispatch
registration, prompt, and response schemas and NIST registration mapping for
both modules. NIST GenVal remains the only execution backend.

## Strict ACVP Policy

- Every new `/acvp/v1` test session is a registration-container session.
- `POST /acvp/v1/testSessions` accepts `algorithms`, `label`,
  `autoGenerateVectorSets`, `campaignSeed`, `testsPerGroup`, `isSample`,
  `expiresInSeconds`, and `metadata`.
- Prompt-based session creation is disabled. `prompt` returns
  `STRICT_REGISTRATION_REQUIRED`; `autoGenerateExpectedResults` returns
  `AUTO_EXPECTED_RESULTS_NOT_SUPPORTED`.
- All generation and validation use NIST ACVP-Server GenVal. There is no local
  generator or local validation fallback reachable through `/acvp/v1`.
- Server responses identify `workflowPolicy: strict` and
  `executionBackend: nist-genval`.
- Clients cannot set `workflowPolicy` or `executionBackend`. There are no
  workflow or generation profile controls in the API or frontend.
- `isSample: true` permits the expected-results endpoint. Non-sample expected
  results remain server-side and return `EXPECTED_RESULTS_NOT_AVAILABLE`.

Legacy records created by earlier local workflows remain readable. Any attempt
to generate, submit, or validate such a record returns
`LEGACY_LOCAL_SESSION_NOT_SUPPORTED`; records are not converted.

The local oracle, validator, expected-result generator, import pipeline, and
demo endpoints have been removed. Production runtime code has no local
generation or validation fallback.

`IUT-tests/mldsa-native/` (ML-DSA / FIPS 204) and `IUT-tests/mlkem-native/`
(ML-KEM / FIPS 203) are external implementation-under-test harnesses; they are
not server oracles. `mlkem-native` derives ACVP responses with the vendored
GiacomoPope/kyber-py implementation in `third_party/kyber-py/` (provenance in
`third_party/kyber-py/KYBER_SOURCE.md`). The repository sample and NIST fixtures
are test inputs only and are not exposed by production endpoints.

## API Workflow

```text
POST /acvp/v1/testSessions
GET  /acvp/v1/testSessions/{sessionId}/vectorSets/{vsId}
POST /acvp/v1/testSessions/{sessionId}/vectorSets/{vsId}/results
GET  /acvp/v1/testSessions/{sessionId}/vectorSets/{vsId}/results
GET  /acvp/v1/testSessions/{sessionId}/results
PUT  /acvp/v1/testSessions/{sessionId}
GET  /acvp/v1/requests/{requestId}
```

The explicit generation endpoint remains available for a session created with
`autoGenerateVectorSets: false`:

```text
POST /acvp/v1/testSessions/{sessionId}/vectorSets/generate
```

Test-session registration and certification use a two-object ACVP
`acvVersion: 1.0` envelope. Bare registration objects remain a deprecated local
compatibility input. Numeric `vsId` is the canonical public vector identity;
internal database UUIDs are not emitted. Certification creates a persistent
request resource in `initial` status because this server is not connected to an
external validation authority. It does not issue a certificate or validation
ID. Obsolete workflow-selection or generation-selection query parameters
return HTTP 400.

## NIST GenVal Adapter

The NIST ACVP-Server source is vendored in `third_party/nist-acvp-server/`.
Provenance is in `third_party/nist-acvp-server/NIST_SOURCE.md`.

```bash
./scripts/nist/copy_nist_genval.sh
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh
```

Runtime settings:

- `ACVP_GENVAL_RUNNER_DLL`
- `ACVP_GENVAL_ARTIFACT_ROOT`
- `ACVP_GENVAL_TIMEOUT_SECONDS`

If the runner is unavailable, generation or validation returns a NIST GenVal
error; the server does not use a Python fallback.

NIST's generated prompt, expected results, and internal projection are stored
as artifacts. The internal projection is never returned by the public API;
expected results are returned only for sample vector sets.

## Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

```bash
cd frontend
npm ci
npm run build
npm run dev
```

The frontend runs at `http://127.0.0.1:5173`; the backend normally runs with:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

## Scope

The backend registry supports ML-DSA `keyGen`, `sigGen`, and `sigVer` for FIPS
204 and ML-KEM `keyGen` and `encapDecap` for FIPS 203. The algorithms endpoint
lists both immutable descriptors, and the ML-KEM module provides strict
registration, prompt, response, mapper, and NIST validation-normalization
contracts.

Frontend FIPS 203 workflows are not implemented. The ML-KEM IUT harness is now
implemented in `IUT-tests/mlkem-native/`, verified against the repository NIST
FIPS 203 fixtures. Mixed ML-DSA/ML-KEM sessions have not been formally supported
or accepted.

Stage 1 details are recorded in
[`docs/stages/stage1-strict-policy.md`](docs/stages/stage1-strict-policy.md).
Stage 2 removal details are recorded in
[`docs/stages/stage2-remove-local-runtime.md`](docs/stages/stage2-remove-local-runtime.md).
Stage 3 architecture details are recorded in
[`docs/stages/stage3-algorithm-neutral-core.md`](docs/stages/stage3-algorithm-neutral-core.md).
Stage 4 ML-KEM GenVal readiness evidence is recorded in
[`docs/stages/stage4-mlkem-genval-readiness.md`](docs/stages/stage4-mlkem-genval-readiness.md).
Stage 5 ML-KEM module details are recorded in
[`docs/stages/stage5-mlkem-algorithm-module.md`](docs/stages/stage5-mlkem-algorithm-module.md).
Stage 7 Priority-0 protocol remediation is recorded in
[`docs/stages/stage7-nist-priority0-interoperability.md`](docs/stages/stage7-nist-priority0-interoperability.md).
