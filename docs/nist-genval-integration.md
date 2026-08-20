# NIST GenVal Integration

`/acvp/v1` uses the pinned NIST ACVP-Server `GenValAppRunner` as its only vector
generation and result validation backend. The registered identities are:

- ML-DSA `keyGen`, `sigGen`, and `sigVer` with `FIPS204`;
- ML-DSA `sigGen` with `FIPS204-tr1`;
- ML-KEM `keyGen` and `encapDecap` with `FIPS203`.

The project does not currently register ML-KEM `FIPS203-tr1`. The official
ML-KEM draft now lists that test revision, but adding it requires a separate
schema, registration and end-to-end acceptance change.

For each requested algorithm object, the service:

1. validates the strict registration and maps it to NIST registration JSON;
2. runs NIST registration checking and generation;
3. stores `registration.json`, `prompt.json`, `expectedResults.json`, and
   `internalProjection.json` in the configured artifact root;
4. returns only the prompt through the public vector-set route; and
5. validates the IUT response using the server-side internal projection.

The internal projection is never exposed by a public endpoint. Expected results
remain server-side; although legacy sample support exists in the backend
protocol, the current frontend does not create sample sessions or expose an
expected-results view.

When the NIST backend cannot complete, the API returns a structured
`NIST_GENVAL_NOT_READY`, `NIST_GENVAL_ARTIFACT_MISSING`, or
`NIST_GENVAL_EXECUTION_ERROR`. It does not use a Python fallback and does not
fall back to any local generator or validator.

## Source and runtime

Vendored source provenance is recorded in
`third_party/nist-acvp-server/NIST_SOURCE.md`. The required commit is
`a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324`.

Docker builds the runner and Orleans host inside the engine image. For native
development only:

```bash
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh
```

Runtime settings are `ACVP_GENVAL_RUNNER_DLL`,
`ACVP_GENVAL_ARTIFACT_ROOT`, and `ACVP_GENVAL_TIMEOUT_SECONDS`. The supported
single-host deployment and its persistent artifact volume are documented in
[`../DEPLOYMENT.md`](../DEPLOYMENT.md).
