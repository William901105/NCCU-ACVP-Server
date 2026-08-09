# ACVP `tr1` support

Verified 2026-08-09 against the current NIST ACVP documentation and official
ACVP-Server source. Here `tr1` means an ACVP **test revision**. It does not
change FIPS 203 or FIPS 204 and is unrelated to ML-DSA's internal `tr = H(pk)`
value. NIST describes each revision as a capability an implementation **MAY**
advertise, so legacy and tr1 registrations remain independently selectable.

## Sources and pin

- ACVP overview and protocol: <https://pages.nist.gov/ACVP/>
- ML-DSA ACVP specification: <https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html>
- ML-KEM ACVP specification: <https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html>
- Official repository: <https://github.com/usnistgov/ACVP-Server>
- Pinned commit: `a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324`
- Nearest upstream release/tag: `v1.1.0.43`
- Git description: `v1.1.0.43-4-ga7f283cd` (latest fetched `master` on
  2026-08-09)
- Relevant implementation paths:
  - `gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-DSA/FIPS204/tr1/SigGen/`
  - `gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-KEM/FIPS203/tr1/EncapDecap/`
- Official fixtures:
  - `gen-val/json-files/ML-DSA-sigGen-FIPS204-tr1/`
  - `gen-val/json-files/ML-KEM-encapDecap-FIPS203-tr1/`

The copy script rejects any source checkout whose HEAD is not the exact pinned
SHA. The build script repeats that check, prints the SHA, and publishes with
`-m:1`; serial MSBuild avoids a restore-graph race observed with this source and
the installed .NET 8 SDK.

## Supported identity matrix

| Algorithm | Mode | Revision | Support |
|---|---|---|---|
| ML-DSA | keyGen | FIPS204 | yes |
| ML-DSA | sigGen | FIPS204 | yes |
| ML-DSA | sigGen | FIPS204-tr1 | yes |
| ML-DSA | sigVer | FIPS204 | yes |
| ML-KEM | keyGen | FIPS203 | yes |
| ML-KEM | encapDecap | FIPS203 | yes |
| ML-KEM | encapDecap | FIPS203-tr1 | yes |

No other tr1 tuple is registered. In particular, ML-DSA keyGen/sigVer tr1 and
ML-KEM keyGen tr1 are rejected as unsupported mode/revision combinations.

## Revision differences

ML-DSA sigGen tr1 adds required registration `keyFormats` values `seed` and/or
`expanded`. Every generated group carries `keyFormat`. An expanded test carries
`sk`; a seed test carries a 32-byte `seed`. The response remains `tcId` plus
`signature`. The IUT derives an expanded key with the independent ML-DSA
implementation's `key_derive(seed)`. Deterministic/randomized signing,
internal/external interfaces, `externalMu`, pure/preHash, context, hash
algorithm, all three parameter sets, and their NIST-supported product remain
intact.

ML-KEM encapDecap tr1 adds registration `keyFormats` values `seed` and/or
`expanded`. Encapsulation consumes `ek,m` and returns `c,k`; decapsulation uses
either expanded `dk,c` or seed components `d,z,c` and returns `k`; key checks
return `testPassed`. The IUT reconstructs seed-form keys through the independent
ML-KEM implementation's `_keygen_internal(d, z)`.

## Text/source/fixture discrepancies

The executable behavior of this pin controls interoperability; differences are
not silently guessed away.

1. The ML-KEM text describes seed-form private material as a `seed`, while the
   GenVal `TestCase`, resolver, and generated prompt use separate 32-byte `d`
   and `z` properties. The project follows `d` plus `z`.
2. The current ML-KEM text makes `functions` and `keyFormats` tr1-oriented, but
   the pinned legacy `v1_0` GenVal parameter validator and official legacy
   registration still require `functions`. Legacy behavior is retained for
   executable compatibility; legacy does not accept `keyFormats`.
3. The ML-DSA test-group table omits `keyFormat`, while its test-case text,
   tr1 source, generated prompt, and fixture require it. The project requires
   it for sigGen tr1 and rejects it for legacy.
4. At commit `a7f283cd`, the checked-in ML-KEM tr1 fixture was corrected after
   v1.1.0.43 so `decapsulationKeyCheck` groups carry `keyFormat: expanded` and
   each test carries `dk`. The generator source was not corrected:
   `TestGroupGeneratorKeyCheckVal` does not set `KeyFormat`; the enum defaults
   to `none`, and `PromptProjectionContractResolver` then emits neither `dk`
   nor `d,z`. A fresh run of the pinned executable reproduced groups containing
   only `tcId`. Non-private-key groups also differ: fresh generation emits
   `keyFormat: none`, while the corrected fixture may omit the property.

The fourth discrepancy is an upstream acceptance blocker for freshly generated
`decapsulationKeyCheck`: an IUT restricted to `prompt.json` cannot decide
`testPassed`. This project accepts the actual prompt shape structurally but the
IUT fails explicitly when key material is absent. It never reads internal or
expected artifacts and never fabricates an empty successful response. The
corrected official fixture proves the expanded `dk` path and remains covered by
tests. Fresh real-oracle acceptance covers the other three functions until NIST
aligns generator source with its corrected fixture.

## Trust boundary

The server validates protocol shape, negotiates exact identities, stores
artifacts, and invokes NIST. It does not compute expected cryptographic answers.
Official NIST GenVal creates `prompt.json`, `internalProjection.json`, and
`expectedResults.json`, and validates responses. The IUT receives only the
prompt and performs ML-DSA/ML-KEM operations using independent libraries.

## Build and acceptance

```bash
bash scripts/nist/copy_nist_genval.sh /path/to/ACVP-Server-at-a7f283cd
bash scripts/nist/build_nist_genval.sh
bash scripts/nist/start_orleans.sh
bash scripts/nist/run_genval.sh check /tmp/case/registration.json
bash scripts/nist/run_genval.sh generate /tmp/case/registration.json

backend/.venv/bin/python IUT-tests/mldsa-native/run_test.py \
  --prompt /tmp/case/prompt.json --response-dir /tmp/case --variant both

bash scripts/nist/run_genval.sh validate \
  /tmp/case/internalProjection.json /tmp/case/response_pass_sigGen.json
```

Run the analogous ML-KEM IUT script for ML-KEM vectors. The IUT command does not
take internal/expected paths. A response mutation is generated with `--variant
both`; official validation must pass the normal response and fail the mutation.

Acceptance executed 2026-08-09 with the binaries built from the pinned source:

| Identity/case | Official groups/tests | Result |
|---|---:|---|
| ML-DSA sigGen FIPS204-tr1, complete registration | 48 / 720 | IUT 720 passed; mutated signature failed |
| ML-KEM encapDecap FIPS203-tr1, encapsulation + decapsulation + encapsulationKeyCheck | 12 / 165 | IUT 165 passed; mutated shared key failed |
| ML-KEM encapDecap FIPS203-tr1, corrected official complete fixture | 15 / 195 | IUT 195 passed; mutations failed, including expanded decapsulationKeyCheck |
| ML-KEM encapDecap FIPS203-tr1, fresh decapsulationKeyCheck | 3 / 30 | blocked by reproduced upstream missing-key defect |
| ML-DSA keyGen FIPS204 | 3 / 75 | passed |
| ML-DSA sigGen FIPS204 | 24 / 360 | passed |
| ML-DSA sigVer FIPS204 | 12 / 180 | passed |
| ML-KEM keyGen FIPS203 | 3 / 75 | passed |
| ML-KEM encapDecap FIPS203 | 12 / 165 | passed |

Official GenVal returns exit code 0 with `disposition: passed`. The mutated tr1
responses returned exit code 13 with `disposition: failed`; the first ML-DSA
failure reason was `Incorrect signature`, and the first ML-KEM reason was
`SharedKey does not match expected valid shared key`.
