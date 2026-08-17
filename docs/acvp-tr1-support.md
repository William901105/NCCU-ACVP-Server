# ACVP `tr1` support

Verified 2026-08-09 against the current NIST ACVP documentation and official
ACVP-Server source. Here `tr1` means an ACVP **test revision**. It does not
change FIPS 204 and is unrelated to ML-DSA's internal `tr = H(pk)`
value. NIST describes each revision as a capability an implementation **MAY**
advertise, so legacy and tr1 registrations remain independently selectable.

## Sources and pin

- ACVP overview and protocol: <https://pages.nist.gov/ACVP/>
- ML-DSA ACVP specification: <https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html>
- Official repository: <https://github.com/usnistgov/ACVP-Server>
- Pinned commit: `a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324`
- Nearest upstream release/tag: `v1.1.0.43`
- Git description: `v1.1.0.43-4-ga7f283cd` (latest fetched `master` on
  2026-08-09)
- Relevant implementation paths:
  - `gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-DSA/FIPS204/tr1/SigGen/`
- Official fixtures:
  - `gen-val/json-files/ML-DSA-sigGen-FIPS204-tr1/`

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

No other tr1 tuple is registered. In particular, ML-DSA keyGen/sigVer tr1 are
rejected as unsupported mode/revision combinations.

## Revision differences

ML-DSA sigGen tr1 adds required registration `keyFormats` values `seed` and/or
`expanded`. Every generated group carries `keyFormat`. An expanded test carries
`sk`; a seed test carries a 32-byte `seed`. The response remains `tcId` plus
`signature`. The IUT derives an expanded key with the independent ML-DSA
implementation's `key_derive(seed)`. Deterministic/randomized signing,
internal/external interfaces, `externalMu`, pure/preHash, context, hash
algorithm, all three parameter sets, and their NIST-supported product remain
intact.

## Text/source/fixture discrepancy

The ML-DSA test-group table omits `keyFormat`, while its test-case text,
   tr1 source, generated prompt, and fixture require it. The project requires
   it for sigGen tr1 and rejects it for legacy.

## Trust boundary

The server validates protocol shape, negotiates exact identities, stores
artifacts, and invokes NIST. It does not compute expected cryptographic answers.
Official NIST GenVal creates `prompt.json`, `internalProjection.json`, and
`expectedResults.json`, and validates responses. The IUT receives only the
prompt and performs the ML-DSA operations using an independent library.

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

The IUT command does not take internal/expected paths. A response mutation is generated with `--variant
both`; official validation must pass the normal response and fail the mutation.

Acceptance executed 2026-08-09 with the binaries built from the pinned source:

| Identity/case | Official groups/tests | Result |
|---|---:|---|
| ML-DSA sigGen FIPS204-tr1, complete registration | 48 / 720 | IUT 720 passed; mutated signature failed |
| ML-DSA keyGen FIPS204 | 3 / 75 | passed |
| ML-DSA sigGen FIPS204 | 24 / 360 | passed |
| ML-DSA sigVer FIPS204 | 12 / 180 | passed |
| ML-KEM keyGen FIPS203 | 3 / 75 | passed |
| ML-KEM encapDecap FIPS203 | 12 / 165 | passed |

Official GenVal returns exit code 0 with `disposition: passed`. The mutated tr1
response returned exit code 13 with `disposition: failed`; the first ML-DSA
failure reason was `Incorrect signature`.
