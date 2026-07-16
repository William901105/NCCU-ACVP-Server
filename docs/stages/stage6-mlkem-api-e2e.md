# Stage 6 ML-KEM API E2E and Live NIST GenVal Acceptance

## Scope and Provenance

- Branch: `feature/stage6-mlkem-api-e2e`
- Base strict SHA and feature start SHA: `0f9550a185870679d511ec1ca7f62df2464325b1`
- Phase A freeze SHA: the commit containing this document; the immutable SHA is pinned in the Phase B audit report.
- Vendored NIST source SHA: `15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0`
- .NET SDK/runtime: `8.0.422` / `8.0.28`
- Python: `3.8.10`; Node: `24.18.0`; npm: `11.16.0`

No ML-KEM IUT, production oracle, local cryptography, or local validation fallback was added. Sample expected results are obtained through the public sample endpoint and used only as known-good test responses. They are not an IUT and are not a production response source.

## Runtime Setup

`scripts/nist/build_nist_genval.sh` published the pinned GenValAppRunner and Orleans ServerHost under ignored `.nist-bin/` paths. `scripts/nist/start_orleans.sh` started one ServerHost process; gateway port 30000 and dashboard port 8081 were checked before live tests. The Linux performance-counter warnings are non-fatal. No bind conflict, duplicate ServerHost, or fatal startup exception was present.

Live tests are skipped unless `NCCU_ACVP_LIVE_GENVAL=1`. The unavailable test additionally requires `NCCU_ACVP_LIVE_GENVAL_UNAVAILABLE=1` and is run separately while the repository-owned Orleans process is stopped.

## API Acceptance

All primary evidence uses FastAPI `TestClient` and public `/acvp/v1` routes. The deterministic test provider is confined to `backend/tests`; it records Check/Generate/Validate boundaries and returns NIST-shaped validation data from immutable Stage 4 fixtures. It is not live parity evidence.

| Scenario | Public operation | Result |
| --- | --- | --- |
| keyGen registration | `POST /acvp/v1/testSessions` | 200, one vector set, three parameter sets |
| encapDecap registration | `POST /acvp/v1/testSessions` | 200, all three sets and four functions |
| explicit generation | `POST .../vectorSets/generate` | 200 once; repeat 409 |
| prompt and sample expected | `GET .../{vectorSetId}` and `GET .../expected` | 200; no internal projection or paths |
| non-sample expected | `GET .../expected` and `showExpected=true` | 403 |
| initial/replacement results | `POST` and `PUT .../results` | 204 after NIST validation |
| vector/session results | `GET .../results` | 200 with passed/fail disposition |
| incomplete session submit | `POST .../submit` | 409 |
| complete and repeated submit | `POST .../submit` | 200 and stable final state |
| post-finalization update | `PUT .../results` | 409 |

Schema-invalid responses covering wrong identity, missing/duplicate IDs, invalid hex/length/type/shape, and unknown fields return 400 before the GenVal validation spy is called. Schema errors, NIST cryptographic failures, and NIST backend failures therefore remain distinct.

## Live NIST Results

Live GenVal generated and validated keyGen and encapDecap vectors for ML-KEM-512, ML-KEM-768, and ML-KEM-1024. Known-good sample responses passed. Length-preserving cryptographic mutations failed at the exact NIST `tcId` for keyGen and for encapsulation, decapsulation, encapsulationKeyCheck, and decapsulationKeyCheck. NIST returned case-level results, and the normalizer preserved that granularity.

A two-mode ML-KEM session produced two one-to-one vector IDs/URLs. Partial submission was rejected; one pass plus one fail aggregated to failed; all-pass deterministic coverage aggregated to validated. Final submit blocked later replacement, and repeated submit returned the same final disposition.

The controlled unavailable run used a five-second runner timeout. It returned `NIST_GENVAL_EXECUTION_ERROR`, did not hang, did not create a partial vector set, did not mark a response passed/failed, and exposed no absolute runner or artifact paths.

## Observed Runtime Corrections

1. **Observed failure:** A sample expected payload copied from the public endpoint was rejected as an unknown-field schema error. **Root cause:** the generic route envelope injected local server metadata into cryptographic prompt/expected payloads. **Minimal correction:** these two public payloads now use a plain ACVP envelope while administrative responses retain server metadata. **Regression:** the keyGen/encapDecap API tests submit the public sample payload unchanged.
2. **Observed failure:** GenVal configuration/artifact/execution errors disclosed absolute `runnerDll` and `artifactRoot` paths. **Root cause:** internal settings were copied into public error details. **Minimal correction:** public errors retain provider identity and relative recovery commands with stable, path-free messages. **Regression:** all three error classes assert sanitized ACVP envelopes and unchanged stored state.
3. **Observed failure:** a real timeout on Python 3.8 raised `TypeError: data must be str, not bytes`. **Root cause:** `TimeoutExpired.stdout/stderr` can be bytes despite text mode. **Minimal correction:** decode timeout output before writing diagnostics. **Regression:** a deterministic bytes-output unit test and the live unavailable API test both pass.
4. **Observed dependency gap:** FastAPI `TestClient` could not import without `httpx`. **Correction:** pin compatible `httpx>=0.27,<1` in backend requirements.

## Verification

```text
python3 -m pytest
  175 passed, 4 skipped in 43.96s

NCCU_ACVP_LIVE_GENVAL=1 python3 -m pytest -q tests/test_stage6_mlkem_live_genval.py
  3 passed, 1 skipped in 59.38s

NCCU_ACVP_LIVE_GENVAL=1 NCCU_ACVP_LIVE_GENVAL_UNAVAILABLE=1 \
  python3 -m pytest -q tests/test_stage6_mlkem_live_genval.py -k unavailable
  1 passed, 3 deselected in 6.62s

npm ci
npm run build
  passed; 34 modules transformed
```

Stage 4 fixture hashes remained unchanged. Frontend FIPS203 remains disabled. Build output, `.nist-bin`, `bin`, and `obj` are ignored and untracked. Detailed sanitized summaries and artifact hashes are in `tests/evidence/stage6/`.

## Known Limitations

- Stage 6 uses sample expected results only as acceptance input because no real ML-KEM IUT exists.
- Validation and generation are synchronous with the current API runtime.
- URL/data-flow protocol conformance is not inferred from runtime success; it is assessed separately in the read-only Phase B audit.
- `npm ci` reports two existing dependency advisories (one moderate and one high); Stage 6 does not apply a breaking audit fix.
