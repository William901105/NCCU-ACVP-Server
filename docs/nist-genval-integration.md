# NIST GenVal Integration

## Architecture

```text
React UI
  |
  | /acvp/v1 strict or nist-conformance
  v
FastAPI acvp_protocol routes
  |
  | service.py
  v
ML-DSA registration mapper
  |
  | single-algorithm NIST registration.json
  v
GenValProvider abstraction
  |
  | dotnet GenValAppRunner
  v
NIST ACVP-Server GenVal + Orleans.ServerHost
  |
  | prompt.json, internalProjection.json, expectedResults.json, validation.json
  v
SQLite metadata + backend/data/acvp-sessions artifact files
```

The Python backend remains the API and storage owner. NIST C# code is vendored
as source under `third_party/nist-acvp-server`; it is not a submodule and is not
started automatically by FastAPI.

## Provider Interface

`backend/app/genval/provider.py` defines the shared adapter boundary:

```text
check_registration(registration, work_dir) -> dict
generate(registration, work_dir) -> GenValArtifacts
validate(internal_projection, response, work_dir) -> Path
```

`NistCliGenValProvider` implements that interface by calling the published
GenValAppRunner DLL with:

- `-c registration.json`
- `-g registration.json`
- `-n internalProjection.json -b response.json`

All paths and timeout settings are centralized in `backend/app/genval/settings.py`.

## Generation Flow

1. The frontend posts an ML-DSA registration container to `/acvp/v1/testSessions`.
2. `acvp_protocol/service.py` validates and negotiates capabilities.
3. Strict workflow, or `generationProfile=nist-conformance`, selects the NIST provider path.
4. `acvp_mldsa/nist_registration_mapper.py` converts each ML-DSA mode into a NIST single-algorithm registration.
5. `NistCliGenValProvider.check_registration()` runs NIST registration checks.
6. `NistCliGenValProvider.generate()` runs vector generation.
7. The backend stores prompt and artifact paths on each vector set.

`expectedResults.json` is stored for debug/sample workflows only. It is not the
formal validation oracle in strict NIST flow.

## Validation Flow

1. The IUT submits response JSON to the vector set results route.
2. The backend validates ACVP response schema with ML-DSA validators.
3. For NIST vector sets, the backend writes `response.json` beside the generation artifacts.
4. `NistCliGenValProvider.validate()` runs GenValAppRunner with the saved `internalProjection.json` and submitted response.
5. `acvp_mldsa/nist_validation_mapper.py` normalizes `validation.json` into the existing frontend/report shape.
6. Strict responses keep ACVP-style disposition output; local debug responses keep the legacy detailed wrapper.

`backend/app/validator.py` remains available for local/debug flows only.

## Artifact Layout

```text
backend/data/acvp-sessions/
  {sessionId}/
    vectorSets/
      {vectorSetId}/
        registration.json
        prompt.json
        internalProjection.json
        expectedResults.json
        check.stdout.txt
        check.stderr.txt
        generation.stdout.txt
        generation.stderr.txt
        response.json
        validation.json
        validation.stdout.txt
        validation.stderr.txt
```

SQLite remains the metadata store. Artifact file paths are recorded in vector
set metadata under `artifactPaths`.

## FIPS203/FIPS204 Merge Strategy

The reusable pieces are algorithm-neutral:

- `backend/app/genval/`
- `scripts/nist/`
- artifact storage layout
- strict workflow routing and error handling
- frontend provider metadata display

Algorithm-specific pieces should stay in algorithm packages:

- ML-DSA registration mapping lives in `backend/app/acvp_mldsa/`.
- A future ML-KEM mapper should live in the FIPS203 package.
- NIST validation normalization can be shared if `validation.json` shape stays common; otherwise each algorithm package should provide a mapper.

This keeps the FastAPI and React application shared while allowing FIPS203 and
FIPS204 teams to own their registration schemas independently.

## Legacy Debug Surfaces

The following remain for compatibility and local debugging:

- `backend/app/crypto_oracle/`
- `/api/oracle/mldsa/*`
- `/api/import/generated*`
- `backend/app/validator.py`
- local workflow with `generationProfile=local-debug`

These are not the formal strict `/acvp/v1` validation oracle.
