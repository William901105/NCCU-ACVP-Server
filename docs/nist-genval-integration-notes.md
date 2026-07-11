# NIST GenVal Integration Notes

## Current Boundary

The public server exposes only the strict `/acvp/v1` workflow and
`/api/health`. ML-DSA registration and schema checks run in the application;
NIST ACVP-Server GenValAppRunner performs generation and IUT-result validation.

1. A registration container is accepted at `POST /acvp/v1/testSessions`.
2. The service maps that registration to NIST ML-DSA registration JSON and
   invokes NIST registration checking and generation.
3. Generation stores `registration.json`, `prompt.json`,
   `expectedResults.json`, and `internalProjection.json` as artifacts.
4. The IUT submits a response to the nested vector-set results endpoint.
5. NIST validates that response using the server-side internal projection and
   emits the final NIST disposition.

No local generator, expected-result generator, or result validator remains in
the production runtime. NIST runner configuration, execution, or artifact
errors are returned directly and never trigger a fallback.

## Artifact Policy

`internalProjection.json` remains server-side because it is the NIST
validation answer file. `expectedResults.json` also remains server-side except
for sample sessions, where the nested expected-results endpoint can return it.
The frontend receives prompts, accepts IUT response files, and displays NIST
result payloads; it does not calculate expected values or dispositions.

## NIST Source and Operations

The NIST source is vendored under `third_party/nist-acvp-server/` with its
provenance recorded in `NIST_SOURCE.md`.

```bash
./scripts/nist/copy_nist_genval.sh
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh
```

Runtime configuration uses `ACVP_GENVAL_RUNNER_DLL`,
`ACVP_GENVAL_ARTIFACT_ROOT`, and `ACVP_GENVAL_TIMEOUT_SECONDS`. The normal
test suite replaces the runner with fixture-backed behavior so it can verify
the strict contract without a live Orleans process. Real GenVal operation
requires a local environment that permits the runner and Orleans host to bind
their required interfaces.
