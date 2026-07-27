# ML-DSA Strict Schema And SHAKE

Phase 5-2 hardens the local ML-DSA schema layer and removes the previous SHAKE half-support state. This is still a local FIPS204 skeleton, not a production ACVP server.

## Strict Schema

The prompt schema now validates fixed-length ML-DSA fields before oracle execution:

- keyGen `seed`: exactly 32 bytes.
- sigGen `sk`: exact parameter-set secret key length.
- sigGen randomized `rnd`: exactly 32 bytes.
- sigGen internal `mu`: exactly 64 bytes.
- sigGen external `context`: at most 255 bytes.
- sigVer `pk`: exact parameter-set public key length.
- sigVer `signature`: exact parameter-set signature length.

The response schema now rejects unknown fields in canonical algorithm response payloads:

- keyGen response group fields: `tgId`, `tests`.
- keyGen response test fields: `tcId`, `pk`, `sk`.
- sigGen response group fields: `tgId`, `tests`.
- sigGen response test fields: `tcId`, `signature`.
- sigVer response group fields: `tgId`, `tests`.
- sigVer response test fields: `tcId`, `testPassed`.

The response validator uses the ML-DSA parameter-set length table to reject pk/sk/signature values that do not match a supported parameter set. For keyGen responses, `pk` and `sk` must correspond to the same parameter set length. `testPassed` must be a JSON boolean, not a string.

Top-level `acvVersion` is accepted because `normalize_acvp_container()` carries the ACVP envelope version into the normalized algorithm body. Top-level `extensions` is the only explicit local extension namespace accepted by the response schema.

## SHAKE PreHash

Phase 5-2 implements SHAKE support rather than rejecting it.

The digest mapping follows the local native oracle wrapper and `mldsa-native` prehash constants:

| hashAlg | Python digest calculation | prehash bytes |
| --- | --- | ---: |
| `SHAKE-128` | `hashlib.shake_128(message).digest(32)` | 32 |
| `SHAKE-256` | `hashlib.shake_256(message).digest(64)` | 64 |

This aligns with `backend/native/mldsa_oracle/siggen_oracle.c` and `sigver_oracle.c`, where `parse_hash_alg()` maps `SHAKE-128` to a 32-byte prehash and `SHAKE-256` to a 64-byte prehash before calling the native HashML-DSA prehash APIs.

With this mapping:

- capability negotiation accepts `SHAKE-128` and `SHAKE-256`;
- vector generation creates external `preHash` groups for SHAKE hash algorithms;
- sigGen expectedResults can sign SHAKE preHash prompts;
- sigVer expectedResults can verify SHAKE preHash prompts;
- `/acvp/v1/algorithms` advertises SHAKE in generated `hashAlgs`.

## Tests

Phase 5-2 tests:

```text
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q tests/conformance/test_mldsa_strict_schema.py
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q tests/conformance/test_mldsa_shake_prehash.py
```

Regression tests should also include:

```text
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q tests/conformance
ACVP_TEST_DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp_test pytest -q
```

## Out Of Scope

Phase 5-2 does not implement FIPS203, frontend work, JWT/login/mTLS, production ACVP lifecycle behavior, vendor/module/OE/dependency resources, or async/large submission handling. It does not modify `/root/ACVP204/mldsa-native` source.
