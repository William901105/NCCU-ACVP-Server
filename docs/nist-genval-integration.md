# NIST GenVal Integration

`/acvp/v1` uses the NIST ACVP-Server `GenValAppRunner` as its only generation
and validation backend for ML-DSA registrations.

For each generated vector set the service:

1. maps the registration container to NIST ML-DSA registration JSON;
2. runs NIST registration checking and generation;
3. stores the generated prompt, expected results, and internal projection as
   server artifacts; and
4. validates the IUT response with the NIST internal projection.

The server returns `NIST_GENVAL_NOT_READY`, `NIST_GENVAL_ARTIFACT_MISSING`, or
`NIST_GENVAL_EXECUTION_ERROR` when that backend cannot complete. It does not
fall back to the Python oracle.

The pre-Stage 1 local implementation remains for later repository cleanup only;
it is unreachable from `/acvp/v1`.
