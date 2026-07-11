# Stage 4: ML-KEM GenVal Readiness

Stage 4 confirms that the vendored NIST ACVP-Server GenVal engine can check
and generate FIPS 203 / ML-KEM vector material. This is readiness evidence,
not product support.

## Scope And Status

The verified NIST GenVal combinations are:

| Mode | Parameter sets | Additional coverage |
| --- | --- | --- |
| `keyGen` | `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024` | All three parameter sets |
| `encapDecap` | `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024` | `encapsulation`, `decapsulation`, `encapsulationKeyCheck`, `decapsulationKeyCheck` |

The application remains ML-DSA-only. Stage 4 does not add an ML-KEM module,
API route, registry descriptor, schema, IUT harness, validator, frontend
enablement, local fallback, database artifact handling, or worker support.

## Provenance

- NCCU strict base commit: `2a351bc189cecafaecaa96bf1cfd91234d42d7b0`.
- Vendored NIST ACVP-Server source commit:
  `15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0`.
- Static-reference source: `https://github.com/hhhylaiii/ACVP-Server` at
  `61b549e51ca18c75c303cf83f6fb58f40c1de700`.
- .NET SDK: `8.0.422`.

Static inspection of the specified reference and the vendored source confirms
ML-KEM FIPS 203 registration validation, key generation,
encapsulation/decapsulation generation, all four function factories, and
Orleans grain integration. This is Decision A: no NIST-source transplant was
needed. No files under `third_party/nist-acvp-server/` were modified.

The reference registrations contain the same algorithm, revision, parameter
sets, and `encapDecap` functions. Stage 4 intentionally uses `isSample: true`
for both captured inputs so that all three generated output artifacts are
available as reproducible evidence.

`scripts/nist/copy_nist_genval.sh` now preserves the existing ML-DSA JSON
directories and additionally copies `ML-KEM-keyGen-FIPS203` and
`ML-KEM-encapDecap-FIPS203`. Its missing-directory warning is algorithm
neutral.

## Captured Evidence

The checked-in evidence is generated directly by NIST GenVal and resides in:

- `tests/fixtures/nist/mlkem/keyGen/`
- `tests/fixtures/nist/mlkem/encapDecap/`

Each directory contains its registration, NIST-produced `prompt.json`,
`internalProjection.json`, and `expectedResults.json`, complete check and
generate stdout/stderr captures, recorded exit codes, and a SHA-256 manifest.
Both `check` and `generate` exited with `0` on
`2026-07-11T13:50:36Z`. Generation ran first in separate temporary work
directories and the resulting files were then copied into the fixture tree.

The runner reported `ML-KEM-KeyGen-FIPS203` and
`ML-KEM-EncapDecap-FIPS203` for their respective operations. The generated
prompt and internal projection preserve all requested parameter sets; the
`encapDecap` artifacts preserve all four requested functions.

## Generated Prompt Shape

`keyGen` produces three AFT groups, one for each parameter set. Each prompt
test case contains `tcId`, `d`, and `z`.

`encapDecap` produces twelve groups: the three parameter sets crossed with the
four requested functions. Its prompt test-case fields are:

| Function | Prompt fields in each test case |
| --- | --- |
| `encapsulation` | `ek`, `m` |
| `decapsulation` | `dk`, `c` |
| `encapsulationKeyCheck` | `ek` |
| `decapsulationKeyCheck` | `dk` |

## Reproducing The Capture

Build the vendored runner, start NIST Orleans in another terminal, then run
each mode in its own work directory. The shell variable avoids recording a
machine-specific project path in fixtures:

```bash
repo_root="$(pwd)"
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh
mkdir -p /tmp/nccu-acvp-stage4/mlkem-keygen
mkdir -p /tmp/nccu-acvp-stage4/mlkem-encapdecap
cp tests/fixtures/nist/mlkem/keyGen/registration.json /tmp/nccu-acvp-stage4/mlkem-keygen/
cp tests/fixtures/nist/mlkem/encapDecap/registration.json /tmp/nccu-acvp-stage4/mlkem-encapdecap/
cd /tmp/nccu-acvp-stage4/mlkem-keygen
"${repo_root}/scripts/nist/run_genval.sh" check registration.json
"${repo_root}/scripts/nist/run_genval.sh" generate registration.json
cd /tmp/nccu-acvp-stage4/mlkem-encapdecap
"${repo_root}/scripts/nist/run_genval.sh" check registration.json
"${repo_root}/scripts/nist/run_genval.sh" generate registration.json
```

The Stage 4 pytest coverage validates the static evidence and copy-script
allowlist without starting Orleans. It deliberately does not turn normal test
runs into a live NIST integration dependency.

## Regression And Limitations

The captured runner stdout includes local Orleans client connection retries
before generation completes. Both operations still exit with `0`, and the
complete stdout/stderr captures are retained in the fixtures. A non-fatal
Orleans Dashboard `:8081` bind conflict was also observed in the capture
environment; it did not prevent the GenVal runner from generating artifacts.

The Stage 4 fixture test validates provenance, hashes, identities, parameter
sets, functions, prompt fields, and copy-script allowlist without requiring
Orleans. The complete backend suite passed with `64 passed`; the frontend
production build passed. ML-DSA behavior was exercised by the full backend
suite and no NIST source changed, so no additional ML-DSA GenVal capture was
required.

ML-KEM remains unavailable to the production registry, API, and frontend. No
response-validation parity or real ML-KEM IUT harness has been established.

## Stage 5 Registration Contract

Stage 5 may begin from the captured registration contract, but must introduce
an ML-KEM module and production registration separately. The supported GenVal
inputs have this shape:

```json
{
  "algorithm": "ML-KEM",
  "mode": "keyGen or encapDecap",
  "revision": "FIPS203",
  "isSample": true,
  "parameterSets": ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
}
```

For `encapDecap`, add `functions` with `encapsulation`, `decapsulation`,
`encapsulationKeyCheck`, and `decapsulationKeyCheck`.
