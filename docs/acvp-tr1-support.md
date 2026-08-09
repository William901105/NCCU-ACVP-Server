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
- Upstream commit date: `2026-07-31T13:00:12-04:00`
- Local compatibility patch:
  `scripts/nist/patches/a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch`
- Patch SHA-256:
  `d421d216a21d0ea38a596342dee6a4144598f33fd40b7b58d4a5916203573ade`
- Relevant implementation paths:
  - `gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-DSA/FIPS204/tr1/SigGen/`
  - `gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-KEM/FIPS203/tr1/EncapDecap/`
- Official fixtures:
  - `gen-val/json-files/ML-DSA-sigGen-FIPS204-tr1/`
  - `gen-val/json-files/ML-KEM-encapDecap-FIPS203-tr1/`

The official upstream `master` still omitted the ML-KEM tr1
`decapsulationKeyCheck` key-format assignment when rechecked on 2026-08-09.
This is therefore not an unmodified official NIST GenVal source tree: it is the
exact official commit above plus one documented compatibility patch. The copy
script rejects any other source SHA, verifies the patch hash, and applies the
patch. The build script rechecks all three facts and publishes with `-m:1`;
serial MSBuild avoids a restore-graph race observed with this source and the
installed .NET 8 SDK. See
`third_party/nist-acvp-server/{NIST_SOURCE,NIST_PATCHES}.md`.

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
   each test carries `dk`, but `TestGroupGeneratorKeyCheckVal` still omitted
   `KeyFormat`. Because `PrivateKeyFormat.None` is the zero/default value,
   `PromptProjectionContractResolver` emitted neither `dk` nor `d,z`. A fresh
   unpatched run reproduced three groups/30 tests with `keyFormat: none` and
   only `tcId`. The local patch assigns `PrivateKeyFormat.Expanded` at that
   test-group metadata source. It does not change enum ordering, projection,
   validation, or the IUT. A focused generation-library test asserts the group
   metadata, and fresh projection tests require `keyFormat: expanded` plus `dk`
   in every `decapsulationKeyCheck` test.

## Trust boundary

The server validates protocol shape, negotiates exact identities, stores
artifacts, and invokes NIST. It does not compute expected cryptographic answers.
The patched NIST GenVal build creates `prompt.json`, `internalProjection.json`,
and `expectedResults.json`, and performs response validation. The IUT receives
only the public prompt and performs ML-DSA/ML-KEM operations using independent
libraries. It has no CLI argument or code path for either internal artifact.

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

| Identity/case | GenVal groups/tests | Result |
|---|---:|---|
| ML-DSA sigGen FIPS204-tr1, complete registration | 48 / 720 | IUT 720 passed; mutated signature failed |
| ML-KEM encapDecap FIPS203-tr1, fresh all-four-function registration | 15 / 195 | prompt-only IUT 195 passed; mutated shared key and decapsulationKeyCheck `testPassed` each failed |
| ML-DSA keyGen FIPS204 | 3 / 75 | passed |
| ML-DSA sigGen FIPS204 | 24 / 360 | passed |
| ML-DSA sigVer FIPS204 | 12 / 180 | passed |
| ML-KEM keyGen FIPS203 | 3 / 75 | passed |
| ML-KEM encapDecap FIPS203 | 12 / 165 | passed |

The patched GenVal returns exit code 0 with `disposition: passed`. Mutated tr1
responses return exit code 13 with `disposition: failed`. The same all-four
ML-KEM flow is also exercised through frontend-shaped registration, backend
schema/mapping, GenVal generation, prompt storage/download, prompt-only IUT,
response submission, GenVal validation, and normalized project results.

The complete backend run, with the task's real tr1 tests enabled, reported
`264 passed, 4 skipped`. Those four are the pre-existing Stage 6 opt-in tests:
the three Orleans-available paths were then enabled separately and reported
`3 passed`, while the Orleans-unavailable path was run after shutdown and
reported `1 passed`. Frontend verification reported 24/24 unit tests, a clean
standalone TypeScript check, and a successful Vite production build. The
focused NIST generation-library metadata test reported 1/1 passed. Python
compileall, shell syntax checks, and diff whitespace checks also passed.
