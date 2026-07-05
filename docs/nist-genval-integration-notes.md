# NIST Gen/Val Integration Notes

## Baseline Static Analysis

`ACVP-FIPS204` is currently a local ACVP-style client workflow and validator, not a full ACVP server. FastAPI exposes local demo/import/oracle routes from `backend/app/main.py`, while canonical `/acvp/v1` routes are mounted from `backend/app/acvp_protocol/routes.py`. New `/acvp/v1` logic should remain in `acvp_protocol`, not move back into `main.py`.

The existing `/acvp/v1` generation flow is:

1. `POST /acvp/v1/testSessions` enters `acvp_protocol/routes.py`.
2. `acvp_protocol/service.py` validates and negotiates the registration with the algorithm provider registry.
3. `MldsaProvider.generate_vector_sets()` calls `acvp_protocol/vector_generation.py`.
4. `vector_generation.py` builds local ML-DSA prompts using deterministic seed derivation and local mutation logic.
5. `MldsaProvider.generate_expected_results()` calls `acvp_mldsa/expected.py`.
6. `expected.py` calls `crypto_oracle/mldsa_oracle.py`, which shells out to local native ML-DSA oracle binaries.
7. SQLite stores session/vector-set metadata, prompt JSON, and expectedResults JSON.

The existing `/acvp/v1` validation flow is:

1. `submit_vector_set_results()` validates ACVP response schema via `validate_mldsa_response()`.
2. `MldsaProvider.validate_results()` calls `backend/app/validator.py`.
3. `validator.py` performs field comparison against expectedResults:
   - keyGen compares `pk` and `sk`.
   - sigGen compares `signature`.
   - sigVer compares `testPassed`.
4. This is suitable only for legacy/debug validation once NIST GenVal is introduced.

## Replacement Boundary

The NIST integration should replace these official `/acvp/v1` workflow pieces:

- `backend/app/acvp_protocol/vector_generation.py`: replace local generation core with NIST registration mapping plus GenVal generation artifacts.
- `backend/app/acvp_protocol/service.py`: store GenVal artifacts and call NIST validation using internalProjection.
- `backend/app/acvp_mldsa/provider.py`: route ML-DSA generation/validation through a GenVal provider instead of local expectedResults comparison for official workflow.
- `backend/app/validator.py`: keep as legacy/debug only; do not use as the formal validation oracle.
- `backend/app/crypto_oracle/`: keep endpoints and helpers for legacy/debug/sample work, but do not use for official `/acvp/v1` validation.

New shared integration points:

- `backend/app/genval/`: provider abstraction, CLI provider, artifact metadata, settings, errors, and validation normalization.
- `backend/app/acvp_mldsa/nist_registration_mapper.py`: maps current ACVP-style ML-DSA selections to NIST GenValAppRunner single-algorithm registration JSON.
- `backend/data/acvp-sessions/`: file-system artifact storage for registration, prompt, internalProjection, expectedResults, response, validation, stdout, and stderr.

## NIST ACVP-Server Findings

The local NIST checkout contains GenValAppRunner at `ACVP-Server/gen-val/samples/GenValAppRunner/src/NIST.CVP.ACVTS.Generation.GenValApp.csproj` and Orleans host at `ACVP-Server/gen-val/samples/NIST.CVP.ACVTS.Orleans.ServerHost/NIST.CVP.ACVTS.Orleans.ServerHost.csproj`.

GenValAppRunner supports:

- check: `-c registration.json`
- generation: `-g registration.json`
- validation: `-n internalProjection.json -b response.json`

Generation writes `internalProjection.json`, `prompt.json`, and `expectedResults.json` beside the registration file. Validation writes `validation.json` beside the response file. `internalProjection.json` must remain server-side and is the formal validation answer file. `expectedResults.json` is debug/sample only.

The ML-DSA NIST sample registrations are present under:

- `ACVP-Server/gen-val/json-files/ML-DSA-keyGen-FIPS204/registration.json`
- `ACVP-Server/gen-val/json-files/ML-DSA-sigGen-FIPS204/registration.json`
- `ACVP-Server/gen-val/json-files/ML-DSA-sigVer-FIPS204/registration.json`

## Frontend Impact

The frontend architecture should not be rewritten. It should continue to call `/acvp/v1` through `frontend/src/api.ts`, use `frontend/src/registry.ts` for FIPS204/FIPS203 selection, and render prompt/upload/results/report flows in the existing React app. Minimal additions should display provider metadata, mark expectedResults as debug/sample only, and surface NIST GenVal/Orleans errors returned by the backend.

## IUT Impact

`IUT-tests/mldsa-native/run_test.py` already accepts direct vector-set payloads and local wrapper payloads. It should remain responsible only for producing ACVP-compatible response JSON from a NIST prompt. It must not read expectedResults or decide pass/fail. Existing fail scripts can continue to mutate generated response JSON for negative testing.
