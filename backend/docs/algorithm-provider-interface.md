# Algorithm Provider Interface

Phase 5-3 adds a minimal algorithm provider boundary for the local `/acvp/v1`
service. The goal is to keep protocol/session flow separate from
algorithm-specific schema, negotiation, vector generation, expectedResults, and
response validation.

This phase does not implement FIPS203, ML-KEM, JWT/mTLS, large submissions,
vendor/module/OE/dependency resources, frontend work, or a production ACVP
workflow.

## Scope

The shared provider layer lives under `app.acvp_core`:

- `algorithm_provider.py` defines `AcvpAlgorithmProvider`.
- `registry.py` defines the provider registry, duplicate detection, lookup, and
  algorithm listing.
- `types.py` keeps shared JSON typing aliases.

Algorithm-specific implementation remains outside `acvp_core`. The current
registered provider is:

| Algorithm | Revision | Modes |
| --- | --- | --- |
| `ML-DSA` | `FIPS204` | `keyGen`, `sigGen`, `sigVer` |

`acvp_core` does not import `acvp_mldsa`. The `/acvp/v1` service bootstraps the
ML-DSA provider at startup/import time and then uses registry lookup for:

- registration container validation
- capability negotiation
- vector generation
- prompt validation
- expectedResults generation
- response validation
- validation result generation

## ML-DSA Provider

`app.acvp_mldsa.provider.MldsaProvider` wraps the existing ML-DSA modules instead
of duplicating schema or crypto code:

- registration validation: `validate_mldsa_registration`
- capability negotiation: `negotiate_mldsa_capabilities`
- vector generation: `generate_vector_sets_from_negotiated_capabilities`
- prompt validation: `validate_mldsa_vector_set`
- expectedResults generation: `generate_expected_results_from_prompt`
- response validation: `validate_mldsa_response`
- result comparison: existing local validator

The provider interface is intentionally not ML-DSA-specific. It does not expose
ML-DSA-only concepts such as `signatureInterface`, `externalMu`, `preHash`, or
`deterministic`.

## FIPS203 Integration Plan

FIPS203 / ML-KEM backend work is not present in this repository phase. When that
backend is merged, it should add a real ML-KEM provider under its own
algorithm-specific package and register it with the shared registry. The
`/acvp/v1` routes should continue to dispatch through the registry rather than
adding route-level FIPS203 branches.

Requests for unregistered algorithms, such as `ML-KEM` before the FIPS203 backend
exists, return a structured unsupported provider error instead of crashing.

## Non-Production Status

This boundary improves extensibility only. It does not make the server a
production ACVP server. The local skeleton still lacks production authentication,
formal ACVP account/resource flows, async/large submission handling, production
database deployment, security hardening, and interoperability validation.

## Tests

Build the native oracle:

```bash
cd NCCU-ACVP-Server/backend/native/mldsa_oracle
make clean
make MLDSA_NATIVE_DIR=/root/ACVP204/mldsa-native
```

Run the provider-focused tests:

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q tests/test_acvp_algorithm_provider.py
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q tests/conformance/test_acvp_algorithm_provider_dispatch.py
```

Run existing conformance tests:

```bash
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q tests/conformance
```
