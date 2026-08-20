# Documentation Index

This index separates current operating guidance from historical implementation
records. Use the current guides for deployment and verification. Stage,
baseline, audit, and evidence files describe the repository at a past freeze
and are not current startup or API instructions.

## Current guides

- [`../README.md`](../README.md): supported algorithms, strict ACVP policy,
  public workflow, and development overview.
- [`../DEPLOYMENT.md`](../DEPLOYMENT.md): supported single-host Docker setup,
  secrets, lifecycle, backup, database access, and offline delivery.
- [`nist-genval-integration.md`](nist-genval-integration.md): pinned NIST
  GenVal boundary, supported algorithm identities, and native runtime setup.
- [`acvp-tr1-support.md`](acvp-tr1-support.md): implemented ML-DSA tr1 scope and
  the explicit ML-KEM tr1 boundary.
- [`mlkem-iut-testing.md`](mlkem-iut-testing.md): current full-stack ML-KEM
  manual acceptance procedure.
- [`../backend/README.md`](../backend/README.md): backend development and test
  entry points.
- [`../backend/docs/persistence-postgresql.md`](../backend/docs/persistence-postgresql.md):
  PostgreSQL configuration, schema ownership, and safety rules.
- [`../frontend/README.md`](../frontend/README.md): frontend development and
  build instructions.

## Historical records

- [`baseline/strict-baseline.md`](baseline/strict-baseline.md): Stage 0
  pre-refactor snapshot.
- [`stages/`](stages/): Stage 1 through Stage 7 implementation records.
- [`audits/stage6-nist-dataflow-url-conformance.md`](audits/stage6-nist-dataflow-url-conformance.md):
  Stage 6 point-in-time audit.
- [`../frontend/docs/stage8-fips203-ui.md`](../frontend/docs/stage8-fips203-ui.md):
  Stage 8 frontend freeze.

Historical evidence under `tests/evidence/` and `frontend/evidence/`, together
with captured fixture output under `tests/fixtures/`, is retained for
reproducibility. It is not an operational runbook.

## Normative references

- [NIST FIPS 203](https://csrc.nist.gov/pubs/fips/203/final)
- [NIST FIPS 204](https://csrc.nist.gov/pubs/fips/204/final)
- [ACVP ML-KEM specification](https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html)
- [ACVP ML-DSA specification](https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html)

The ACVP drafts evolve independently of this repository. The supported
revision matrix in the root README and runtime algorithm descriptor endpoint
remain authoritative for this implementation.
