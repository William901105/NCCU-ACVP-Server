# NCCU ACVP Server

NCCU ACVP Server provides local ACVP workflows and validation for FIPS 204 / ML-DSA.

The current release is a local implementation, not a full production ACVP server.

Production ACVP server behavior is intentionally out of scope for this MVP.

## Project Purpose

NCCU ACVP Server supports these local ACVP-style flows:

- capability registration
- test session and vector set creation
- prompt JSON download/import
- IUT response JSON upload
- local validation and report export

Strict ML-DSA `/acvp/v1` sessions use the vendored NIST ACVP-Server GenVal
adapter when the .NET runner has been built. Local debug sessions still keep the
Python/native oracle path for development and sample workflows.

## Current Scope

- ML-DSA / keyGen / FIPS204
- ML-DSA / sigGen / FIPS204
- ML-DSA / sigVer / FIPS204
- Registry-driven frontend selection for FIPS versions
- FIPS203 is visible in the UI as `開發中` and operations are disabled
- Local `/acvp/v1/testSessions` and `/acvp/v1/vectorSets` lifecycle
- ACVP top-level object format
- ACVP top-level array format with an `acvVersion` object followed by a vector-set object
- Local comparison by `tgId` and `tcId`
- `keyGen`: compare `pk` and `sk`
- `sigGen`: compare `signature`
- `sigVer`: compare `testPassed`
- NIST GenVal artifact storage for strict ML-DSA vector generation and validation
- Result states: `passed`, `failed`, `missing`, `malformed`
- JSON and Markdown report export
- IUT response state labels: `waiting`, `loaded`, `ready`, and `error`
- Client-side `campaignSeed` validation matching the backend 32-128 hex character rule

## Out Of Scope

- Login or JWT
- Vendor, module, or OE management
- NIST Demo ACVTS connection
- Production ACVP protocol compliance
- FIPS203 / ML-KEM operations

## Project Structure

```text
NCCU-ACVP-Server/
  backend/
    app/
      main.py
      models.py
      acvp_parser.py
      validator.py
      report.py
      sample_loader.py
    requirements.txt
  frontend/
    src/
      App.tsx
      api.ts
      registry.ts
      types.ts
      components/
        Dashboard.tsx
        JsonUpload.tsx
        VectorSetViewer.tsx
        TestGroupTable.tsx
        TestCaseDetail.tsx
        ValidationSummary.tsx
        FailureList.tsx
        ReportViewer.tsx
        JsonViewer.tsx
  sample-data/
    ML-DSA-keyGen-FIPS204/
    ML-DSA-sigGen-FIPS204/
    ML-DSA-sigVer-FIPS204/
  IUT-tests/
    mldsa-native/
      run_test.py
      run_keygen.py
      run_keygen_fail.py
      run_siggen.py
      run_siggen_fail.py
      run_sigver.py
      run_sigver_fail.py
      prompt/
      response/
```

## Install Backend

```bash
cd NCCU-ACVP-Server/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd NCCU-ACVP-Server/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Start Backend

```bash
cd NCCU-ACVP-Server/backend
uvicorn app.main:app --reload --port 8000
```

The same command also works from the project root:

```bash
cd NCCU-ACVP-Server
uvicorn app.main:app --reload --port 8000
```

The backend enables CORS for `localhost:5173`, `127.0.0.1:5173`, `localhost:3000`, and `127.0.0.1:3000`.

## NIST GenVal Adapter

The NIST ACVP-Server source is vendored under:

```text
third_party/nist-acvp-server/
```

The copy is source-only and excludes `.git`, `bin`, and `obj`. Provenance is
recorded in `third_party/nist-acvp-server/NIST_SOURCE.md`.

Build and run the adapter with:

```bash
cd NCCU-ACVP-Server
./scripts/nist/copy_nist_genval.sh
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh
```

`scripts/nist/run_genval.sh` is a thin wrapper around the built
`GenValAppRunner` for manual check/generate/validate calls.

Runtime settings:

- `ACVP_GENVAL_RUNNER_DLL`: override the built `GenValAppRunner` DLL path
- `ACVP_GENVAL_ARTIFACT_ROOT`: override artifact storage, default `backend/data/acvp-sessions`
- `ACVP_GENVAL_TIMEOUT_SECONDS`: CLI timeout, default `120`

Strict workflow behavior:

- `workflowProfile=strict` or `generationProfile=nist-conformance` maps ML-DSA registration JSON into NIST registration JSON.
- Generation calls NIST GenVal check/generate and stores `registration.json`, `prompt.json`, `internalProjection.json`, `expectedResults.json`, stdout, and stderr.
- Validation calls NIST GenVal with `internalProjection.json` and the submitted response JSON.
- `internalProjection.json` is the formal server-side validation artifact.
- `expectedResults.json` is retained only for debug/sample inspection and is not used as the formal strict validator.

Local workflow behavior:

- `workflowProfile=local` with `generationProfile=local-debug` keeps the legacy Python/native oracle path.
- `backend/app/validator.py` and `backend/app/crypto_oracle/` are legacy/debug support for this local path.

If `.NET 8` is not installed or the runner has not been built, strict generation
returns `NIST_GENVAL_NOT_READY` with the expected build/start commands in the
error details.

## Install Frontend

```bash
cd NCCU-ACVP-Server/frontend
npm install
```

## Start Frontend

```bash
cd NCCU-ACVP-Server/frontend
npm run dev
```

Vite serves the frontend on port `5173` by default.

## Sample Data

The included sample data is copied from the local reference repository under:

```text
ACVP-Server/gen-val/json-files/
```

Included sample sets:

- `ML-DSA-keyGen-FIPS204`
- `ML-DSA-sigGen-FIPS204`
- `ML-DSA-sigVer-FIPS204`

Each sample directory includes:

- `prompt.json`
- `expectedResults.json`
- `response.pass.json`
- `response.fail.json`

`response.pass.json` matches `expectedResults.json`. `response.fail.json` intentionally changes the first relevant field in the first test case.

## ACVP Client Workflow

Both the `strict` NIST GenVal path and the legacy `local` path are currently
available. Later refactor stages will remove the legacy local path; this Stage
0 baseline intentionally keeps both paths and their existing APIs.

1. Start the backend.
2. Start the frontend.
3. Select `FIPS 204 / ML-DSA` in the Registry panel.
4. Select one or more modes and parameter sets.
5. Enter a valid campaign seed or leave it empty for the deterministic fallback.
6. Click `Register capabilities`.
7. Download the prompt JSON from the active vector set.
8. Generate an IUT response with `IUT-tests/mldsa-native/run_test.py`.
9. Upload the response JSON in the IUT Response panel.
10. Click `Validate response`, then export JSON or Markdown from Validation Report.

The frontend calls:

```text
GET  /acvp/v1/testSessions
POST /acvp/v1/testSessions
GET  /acvp/v1/testSessions/{sessionId}/vectorSets
GET  /acvp/v1/vectorSets/{vectorSetId}
POST /acvp/v1/vectorSets/{vectorSetId}/results
```

## IUT Response States

The IUT Response chip reports the local upload/validation state:

- `waiting`: no response JSON is loaded
- `ready`: a response JSON file has been selected and is ready to submit
- `loaded`: the response has been sent to the local ACVP endpoint and is in transit
- `error: Wrong response format!`: the uploaded response failed schema/mode validation

The response file input is reset after each selection, so the same
`response_pass_<mode>.json` file can be uploaded repeatedly across newly created
test sessions.

## Campaign Seed Validation

For registration-generated vector sets, `campaignSeed` must contain only
hexadecimal characters, must not contain whitespace, must have even length, and
must be between 32 and 128 hex characters. Empty input is allowed and uses the
backend deterministic fallback seed.

## IUT Scripts

The IUT helpers live in `IUT-tests/mldsa-native/` and use the sibling
`../mldsa-native` checkout as the implementation under test.

```bash
cd NCCU-ACVP-Server/IUT-tests/mldsa-native
python3 run_test.py --prompt prompt/prompt-keygen.json
python3 run_keygen.py --prompt prompt/prompt-keygen.json
python3 run_keygen_fail.py --prompt prompt/prompt-keygen.json
```

Generated files are written to `response/response_pass_<mode>.json` and
`response/response_fail_<mode>.json`. Prompt and response JSON files in the IUT
test folders are ignored by git.

## Run Validation

Click `Validate`.

The validator:

- Aligns expected and response test cases by `tgId` and `tcId`
- Marks missing response test cases as `missing`
- Marks missing required response fields as `malformed`
- Marks mismatched values as `failed`
- Marks exact matches as `passed`

The frontend calls:

```text
POST /api/validate
```

## Export Report

Click `Report` after loading or importing a bundle. The Report Export panel can download:

- `report-<importId>.json`
- `report-<importId>.md`

The frontend calls:

```text
GET /api/report/{importId}
```

## API Summary

```text
GET  /api/health
POST /api/import
POST /api/validate
GET  /api/import/{importId}
GET  /api/report/{importId}
GET  /api/sample-data
POST /api/load-sample
GET  /acvp/v1/version
GET  /acvp/v1/algorithms
GET  /acvp/v1/testSessions
POST /acvp/v1/testSessions
GET  /acvp/v1/testSessions/{sessionId}
GET  /acvp/v1/testSessions/{sessionId}/vectorSets
GET  /acvp/v1/testSessions/{sessionId}/results
GET  /acvp/v1/vectorSets/{vectorSetId}
GET  /acvp/v1/vectorSets/{vectorSetId}/expectedResults
POST /acvp/v1/vectorSets/{vectorSetId}/results
```

## Roadmap

- Add an ML-DSA oracle integration point
- Add a NIST GenValAppRunner wrapper integration point
- Add a simplified session API
- Add optional persisted import sessions
- Add a full ACVP-compatible API layer as a separate future milestone
