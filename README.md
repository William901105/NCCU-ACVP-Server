# NCCU ACVP Server

NCCU ACVP Server exposes a strict-only ACVP v1 workflow for FIPS 204 / ML-DSA.

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

The legacy local oracle, validator, import and demo endpoints remain in the
repository for Stage 2 removal, but are not part of the `/acvp/v1` runtime path.

## API Workflow

```text
POST /acvp/v1/testSessions
GET  /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}
POST /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results
GET  /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results
GET  /acvp/v1/testSessions/{sessionId}/results
```

The explicit generation endpoint remains available for a session created with
`autoGenerateVectorSets: false`:

```text
POST /acvp/v1/testSessions/{sessionId}/vectorSets/generate
```

All normal `/acvp/v1` responses use an ACVP `acvVersion: 1.0` envelope. Obsolete
workflow-selection or generation-selection query parameters return HTTP 400.

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

Supported protocol work is ML-DSA `keyGen`, `sigGen`, and `sigVer` for FIPS 204.
ML-KEM / FIPS 203 is not part of this project stage.

Stage 1 details are recorded in
[`docs/stages/stage1-strict-policy.md`](docs/stages/stage1-strict-policy.md).
