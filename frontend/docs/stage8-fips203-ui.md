# Stage 8 FIPS 203 Frontend Enablement

## Scope and baseline

- Base `strict` SHA: `d6e27208d9fb40553abe432d5dfb421032a07c70`.
- Stage 8 changes are limited to `frontend/**`.
- No backend, NIST GenVal, SQLite, fixture, root documentation, or Stage 6/7 file is changed.

## Frontend workflow

The registration panel has a keyboard-operable FIPS selector for FIPS 204 / ML-DSA and FIPS 203 / ML-KEM. Switching the selector restores the selected algorithm's registration defaults without clearing a loaded historical test session. Session and vector metadata continue to come from backend responses.

FIPS 203 exposes `keyGen` and `encapDecap`, the ML-KEM-512/768/1024 parameter sets, and these `encapDecap` functions:

- `encapsulation`
- `decapsulation`
- `encapsulationKeyCheck`
- `decapsulationKeyCheck`

The pure registration builder emits one algorithm object per selected mode. ML-KEM `keyGen` does not include functions, while `encapDecap` requires a non-empty selected function set. ML-DSA keeps its existing key generation and signature capability fields; no signature-only fields are emitted for ML-KEM.

## Protocol alignment

- Session registration and certification PUT requests use the canonical two-member ACVP 1.0 envelope.
- A raw uploaded IUT response is wrapped once in an ACVP envelope. An already canonical response is sent unchanged.
- Public vector routes and state use numeric `vsId`; the frontend does not use legacy UUID vector routes.
- Prompt, expected, vector result, session result, and request-resource views retain the complete raw server envelope.
- Request polling accepts only `/acvp/v1/requests/{numericId}`.

## Downloads and certification

The vector workspace can download the complete prompt envelope, sample-only expected envelope, vector results, and session results through Blob object URLs. Filenames contain the public algorithm, mode, and numeric `vsId` and are sanitized before download.

Certification inputs start empty and accept only single-resource module and OE URLs. Submission is enabled only when the active backend session is passed and publishable and both references are valid. The UI sends an empty `algorithmPrerequisites` array, displays only backend-provided request state, and polls the returned relative request URL. It does not call the local session `/submit` route or create certificate identifiers.

## Boundaries

- No local oracle or IUT implementation is added.
- No expected result is converted into an IUT response.
- No local validation fallback is added.
- No mixed ML-DSA/ML-KEM registration session is supported.
- No certification or NIST/CAVP approval is claimed.

## Verification

Commands run for Stage 8:

```text
cd frontend
npm ci
npm test
npm run build
npm run preview

cd ../backend
pytest
```

Results are recorded in `frontend/evidence/stage8/test-execution.txt`. The backend test runner was loaded from a temporary Python 3.8-compatible dependency directory because `pytest` was not installed on the system PATH; this did not modify the repository.

## Known limitations

- No real ML-KEM IUT implementation.
- No frontend generation of cryptographic responses.
- No external certification authority.
- No mixed ML-DSA/ML-KEM registration session.
- F-04 through F-09 backend audit items remain outside Stage 8.
- The existing Vite 5 toolchain has one moderate and one high npm audit advisory. Resolving them requires a major Vite upgrade and is outside this scoped stage. Vitest was upgraded to a release without the initially reported Vitest advisory.
