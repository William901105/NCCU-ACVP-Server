# NIST GenVal Integration

`/acvp/v1` uses the NIST ACVP-Server `GenValAppRunner` as its only generation
and validation backend for supported ML-DSA and ML-KEM registrations.

For each generated vector set the service:

1. maps the registration container to NIST registration JSON;
2. runs NIST registration checking and generation;
3. stores the generated prompt, expected results, and internal projection as
   server artifacts; and
4. validates the IUT response with the NIST internal projection.

The server returns `NIST_GENVAL_NOT_READY`, `NIST_GENVAL_ARTIFACT_MISSING`, or
`NIST_GENVAL_EXECUTION_ERROR` when that backend cannot complete. It does not
fall back to any local generator or validator.

The vendored base is official NIST commit
`a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324`. Its current upstream ML-KEM
FIPS203-tr1 group generator omits the `decapsulationKeyCheck` `KeyFormat`, so
this project applies one hash-pinned local compatibility patch which sets the
group to `Expanded`. This is not an unmodified official NIST GenVal source tree;
full provenance is recorded in
`third_party/nist-acvp-server/NIST_SOURCE.md` and `NIST_PATCHES.md`.

`internalProjection` is a server-side artifact used only for NIST validation.
It is not exposed by a public endpoint. `expectedResults` is also held
server-side and can be fetched only for sample vector sets.
