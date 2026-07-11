# Strict Refactor Baseline

This document records the Stage 0 baseline for NCCU ACVP Server before the
strict-only refactor.

## Git and Environment

- Starting branch: `feat/nist-genval-adapter`
- Starting commit: `a16afec310b6acb604193e18dab4ee57e9bc06d2`
- Baseline tag: `pre-strict-refactor`
- Baseline branch created from that commit: `strict`
- Capture date: `2026-07-11`
- Python: `3.8.10`
- pytest: `8.2.2`
- Node.js: `v24.18.0`
- npm: `11.16.0`
- .NET SDK: `8.0.422`
- NIST source commit: `15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0`

The repository vendors NIST Gen/Val source under
`third_party/nist-acvp-server/`; it is copied source, not a git submodule.

## Start and Test Commands

Backend:

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd NCCU-ACVP-Server/frontend
npm ci
npm run dev
```

Baseline checks:

```bash
cd NCCU-ACVP-Server/backend
pytest

cd ../frontend
npm ci
npm run build

cd ..
bash -n scripts/baseline/capture_strict_baseline.sh
```

NIST GenVal build, Orleans startup, and manual runner usage:

```bash
./scripts/nist/copy_nist_genval.sh
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh

./scripts/nist/run_genval.sh check path/to/registration.json
./scripts/nist/run_genval.sh generate path/to/registration.json
./scripts/nist/run_genval.sh validate path/to/internalProjection.json path/to/response.json
```

The GenVal runner is
`.nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll`. The Orleans
host is
`.nist-bin/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll`.

## Existing API Surface

The complete pre-strict OpenAPI document is preserved in
`docs/baseline/openapi-pre-strict.json`. The existing canonical ACVP routes are:

- `GET /acvp/v1/version`
- `GET /acvp/v1/algorithms`
- `GET|POST /acvp/v1/testSessions`
- `GET|DELETE /acvp/v1/testSessions/{sessionId}`
- `GET /acvp/v1/testSessions/{sessionId}/vectorSets`
- `POST /acvp/v1/testSessions/{sessionId}/vectorSets/generate`
- `GET|DELETE /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}`
- `GET /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/expected`
- `GET|POST|PUT /acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results`
- `GET /acvp/v1/testSessions/{sessionId}/results`
- `POST /acvp/v1/testSessions/{sessionId}/submit`
- `GET|DELETE /acvp/v1/vectorSets/{vectorSetId}`
- `GET /acvp/v1/vectorSets/{vectorSetId}/expectedResults`
- `GET|POST /acvp/v1/vectorSets/{vectorSetId}/results`

Legacy local routes remain available, including `/api/import`,
`/api/validate`, `/api/load-sample`, `/api/demo/acvp/test-sessions`,
`/api/demo/clear`, and the `/api/oracle/mldsa/*` endpoints. Stage 0 does not
remove or change their request/response behavior.

## Workflow Baseline

The `strict` workflow uses canonical nested `/acvp/v1` routes, NIST GenVal
generation and validation, hidden server-side `internalProjection.json`,
sample-only expected results, and 204 result submission followed by a results
read. `generationProfile=nist-conformance` selects the NIST fixture profile.

The legacy `local` workflow uses the local skeleton wrappers, local
`crypto_oracle` expected-result generation, downloadable expected results, and
the existing `validator.py` comparison path. Both paths intentionally coexist
in this baseline; a later stage will remove the legacy local path.

## Runtime Artifacts

- SQLite database: `backend/data/acvp.sqlite3`
- Strict GenVal artifacts: `backend/data/acvp-sessions/{sessionId}/vectorSets/{vectorSetId}/`
- NIST runner output: `.nist-bin/genval-runner/`
- Orleans output: `.nist-bin/orleans-server/`
- Golden fixture output: `tests/fixtures/nist/mldsa/{keyGen,sigGen,sigVer}/`

The strict artifact directory contains registration, prompt,
`internalProjection.json`, expected results for debug/sample inspection,
submitted response, validation output, and runner logs. Absolute development
paths are not part of the golden fixtures.

## Known Limitations

- The application is not a production ACVP server and has no authentication,
  JWT/mTLS, vendor/module/OE management, or production database deployment.
- NIST strict generation and validation require the .NET runner and a reachable
  Orleans.ServerHost.
- ML-KEM/FIPS203 is not implemented; its disabled registry entry is retained as
  an explicit development placeholder and does not claim support.
- The legacy local workflow, local oracle, validator, demo routes, and import
  routes are intentionally still present in Stage 0.

## Stage 0 Statement

Stage 0 establishes a strict-only refactor baseline and does not change
runtime workflow behavior, ACVP request/response semantics, database schema,
provider interfaces, cryptographic implementation, or the existence of the
legacy local workflow. Product naming and provenance documentation are updated
to `NCCU-ACVP-Server` / `NCCU ACVP Server`; the OpenAPI and storage snapshots
record the pre-strict application state.
