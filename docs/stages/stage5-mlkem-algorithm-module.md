# Stage 5: FIPS 203 ML-KEM Algorithm Module

## Goal And Base

Stage 5 adds a production algorithm module for ML-KEM without changing the
algorithm-neutral protocol, GenVal, or storage layers. Work started from strict
commit `757ea108337bd237d9fca640477549892ccefdc5`, after the Stage 4 readiness
test passed.

The provider is `nist-ml-kem-fips203` and supports these identities:

- `ML-KEM / keyGen / FIPS203`
- `ML-KEM / encapDecap / FIPS203`

NIST GenVal remains the only generation and validation backend. The module
performs JSON validation, capability negotiation, registration mapping, and
validation-result normalization only; it contains no cryptographic operation,
expected-result generator, local oracle, or fallback.

## Descriptor

The immutable descriptor advertises:

- modes: `keyGen`, `encapDecap`
- parameter sets: `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024`
- functions: `encapsulation`, `decapsulation`,
  `encapsulationKeyCheck`, `decapsulationKeyCheck`
- registration and response schemas: `draft-celi-acvp-ml-kem-01`
- execution backend: `nist-genval`

The encoded-object sizes were cross-checked against FIPS 203 Table 3, the
vendored NIST `MLKEMParameters.cs`, and the immutable Stage 4 prompt and
expected-results fixtures. All three sources agree:

| Parameter set | Encapsulation key | Decapsulation key | Ciphertext |
| --- | ---: | ---: | ---: |
| ML-KEM-512 | 800 bytes | 1632 bytes | 768 bytes |
| ML-KEM-768 | 1184 bytes | 2400 bytes | 1088 bytes |
| ML-KEM-1024 | 1568 bytes | 3168 bytes | 1568 bytes |

The `d`, `z`, `m`, and shared-secret `k` fields are each 32 bytes.

## Registration Contract

Both modes require `algorithm`, `mode`, `revision`, and a non-empty, unique
`parameterSets` array. `prereqVals` is optional and each item is strictly an
`algorithm`/`valValue` string pair. Only `encapDecap` accepts a non-empty,
unique `functions` array. Unknown fields, values, duplicates, and malformed
types are rejected with `AcvpSchemaError` codes and exact JSON paths.
ML-KEM `prereqVals` accepts only the official prerequisite algorithm
identifiers `SHA` and `DRBG`. `valValue` remains a non-empty validation
identifier or `same`.

Capability negotiation preserves client ordering and returns only capabilities
that the validated registration requested. It does not add parameter sets or
functions.

## Prompt Schema

The prompt validator accepts object and NIST array containers. It validates
the ML-KEM identity, optional sample metadata, non-empty groups, and globally
unique `tgId` and `tcId` values.

- key generation uses AFT cases containing exact 32-byte `d` and `z` values.
- encapsulation uses AFT cases with a parameter-specific `ek` and 32-byte `m`.
- decapsulation uses VAL cases with parameter-specific `dk` and `c` values.
- key checks use VAL cases containing only `ek` or `dk`.

Key-check encoded keys require non-empty valid hexadecimal input but do not
require the normal encoded-object length. NIST deliberately supplies malformed
keys, including abnormal lengths, to test IUT key validation; the Stage 4
golden prompt contains these cases.

## Response Schema

Response groups contain only `tgId` and tests, with IDs unique across the full
response. Identity fields are optional but are validated when present.

- key generation returns matching parameter-set `ek` and `dk` values.
- encapsulation returns a supported-length `c` and 32-byte `k`.
- decapsulation returns a 32-byte `k`.
- either key-check function returns a JSON boolean `testPassed`.

The mode can be supplied by protocol dispatch, a top-level field, or inferred
from response shape. Every case in one group must have the same shape.

## NIST Mapping And Normalization

The mapper emits only the NIST registration fields required by the selected
mode, plus caller-provided prerequisites. Mapping Stage 4 registrations after
removing `vsId` and `isSample`, then restoring those arguments, produces exact
fixture equality for both modes.

The validation normalizer propagates prompt identity metadata, records the
`nist-genval` provider and NIST disposition, produces protocol summary counts,
and retains each original NIST test result. Only a case result equal to
`passed`, case-insensitively, is normalized as passed.

## Bootstrap And Boundaries

`acvp_core/bootstrap.py` is the only composition root importing both concrete
modules. It registers ML-DSA first and ML-KEM second; descriptor output remains
deterministically sorted by the registry. The production registry now contains
two providers and five identities.

AST dependency tests verify that `algorithms/mlkem` does not import ML-DSA,
FastAPI, storage, GenVal, or subprocess. The protocol service, GenVal adapter,
storage implementation, ML-DSA package, frontend source, and Stage 4
cryptographic evidence are unchanged.

## Verification

- Stage 4 preflight: `6 passed`
- focused ML-KEM tests: `96 passed`
- full backend test suite: `161 passed`
- frontend dependency install and production build: passed (`tsc --noEmit` and
  Vite production build)
- Stage 4 keyGen and encapDecap registration/prompt/expected-results fixtures
  are consumed directly as immutable golden inputs
- prerequisite allowlist coverage accepts `SHA` and `DRBG` and rejects aliases
- Stage 4 tracked logs have an expanded Orleans/runtime failure-token guard
- symmetric key-check tests accept abnormal encoded-key lengths while rejecting
  malformed hexadecimal input and invalid field shapes

The Stage 5 suite covers module delegation, descriptor metadata, registration,
capability negotiation, prompts, responses, NIST mapping, validation
normalization, production registry composition, and dependency boundaries.

## Known Limitations And Stage 6

Stage 5 does not establish full live API generation/upload/validation
acceptance, response pass/fail parity with live NIST GenVal, a real ML-KEM IUT
harness, frontend FIPS 203 workflow support, or mixed ML-DSA/ML-KEM session
support. Stage 6 is responsible for those E2E acceptance activities and any
runtime integration fixes they reveal.
