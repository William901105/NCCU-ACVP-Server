# ML-DSA keyGen expectedResults generation

This backend currently supports:

- ML-DSA keyGen native oracle binaries backed by `mldsa-native`.
- `POST /api/oracle/mldsa/keygen` for a single deterministic keyGen oracle call.
- `POST /api/oracle/mldsa/keygen/expected-results` for generating keyGen `expectedResults` from an ACVP-style keyGen prompt.
- `POST /api/oracle/mldsa/expected-results` for generating keyGen, sigGen, or sigVer `expectedResults` from an ACVP-style prompt.
- `POST /api/import/generated` and `POST /api/import/generated-and-validate` for generated expectedResults import flows.
- `/api/demo/acvp/test-sessions` endpoints for a PostgreSQL-backed local demo lifecycle.
- `POST /api/import/generated-keygen` for importing a prompt plus response while generating keyGen `expectedResults` server-side.
- `POST /api/oracle/mldsa/siggen` for single-case internal and external sigGen oracle calls.
- `POST /api/oracle/mldsa/sigver` for single-case internal and external sigVer oracle calls.

This is still a local demo service, not a formal ACVP server.

## Build native oracle

```bash
cd backend/native/mldsa_oracle
make clean
make MLDSA_NATIVE_DIR=/root/ACVP204/mldsa-native
```

The build creates:

```text
bin/mldsa44_keygen_oracle
bin/mldsa65_keygen_oracle
bin/mldsa87_keygen_oracle
bin/mldsa44_siggen_oracle
bin/mldsa65_siggen_oracle
bin/mldsa87_siggen_oracle
bin/mldsa44_sigver_oracle
bin/mldsa65_sigver_oracle
bin/mldsa87_sigver_oracle
```

## Test the C oracle

```bash
cd backend/native/mldsa_oracle
./bin/mldsa44_keygen_oracle 000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F
```

The output is JSON with `pk` and `sk`.

## Call the single-case sigGen endpoint

The sigGen oracle supports ACVP internal signing:

- `signatureInterface = "internal"`
- `externalMu = false` with `message`
- `externalMu = true` with `mu`
- `deterministic = true` with fixed all-zero internal `rnd`
- `deterministic = false` with caller-provided ACVP `rnd`

It also supports ACVP external signing:

- `signatureInterface = "external"`
- `preHash = "pure"` with `message`
- `preHash = "preHash"` with `message` plus `hashAlg`
- `context` as a hex string from 0 to 255 bytes
- `externalMu` and `mu` are not allowed
- `deterministic = true` uses fixed all-zero native `rnd`
- `deterministic = false` requires caller-provided 32-byte `rnd`

It uses the mldsa-native `signature_internal` API with an empty prefix. The
server never generates randomness for `deterministic=false`; the request must
provide a 32-byte `rnd`. When `externalMu=true`, the request uses a 64-byte
`mu` instead of `message`.

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/siggen \
  -H "Content-Type: application/json" \
  -d '{
    "parameterSet": "ML-DSA-44",
    "signatureInterface": "internal",
    "externalMu": false,
    "deterministic": true,
    "sk": "PUT_SECRET_KEY_HEX_HERE",
    "message": "00010203040506070809"
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/siggen \
  -H "Content-Type: application/json" \
  -d '{
    "parameterSet": "ML-DSA-44",
    "signatureInterface": "internal",
    "externalMu": true,
    "deterministic": false,
    "sk": "PUT_SECRET_KEY_HEX_HERE",
    "mu": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F202122232425262728292A2B2C2D2E2F303132333435363738393A3B3C3D3E3F",
    "rnd": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/siggen \
  -H "Content-Type: application/json" \
  -d '{
    "parameterSet": "ML-DSA-44",
    "signatureInterface": "external",
    "deterministic": true,
    "sk": "PUT_SECRET_KEY_HEX_HERE",
    "message": "00010203040506070809",
    "preHash": "pure",
    "context": ""
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/siggen \
  -H "Content-Type: application/json" \
  -d '{
    "parameterSet": "ML-DSA-44",
    "signatureInterface": "external",
    "deterministic": false,
    "sk": "PUT_SECRET_KEY_HEX_HERE",
    "message": "00010203040506070809",
    "preHash": "preHash",
    "context": "0A0B0C",
    "hashAlg": "SHA2-256",
    "rnd": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
  }'
```

## Call the single-case sigVer endpoint

The sigVer oracle supports ACVP internal verification:

- `signatureInterface = "internal"`
- `externalMu = false` with `message`
- `externalMu = true` with `mu`

It also supports ACVP external verification:

- `signatureInterface = "external"`
- `preHash = "pure"` with `message`
- `preHash = "preHash"` with `message` plus `hashAlg`
- `context` as a hex string from 0 to 255 bytes
- `externalMu` and `mu` are not allowed

It uses the mldsa-native `verify_internal` API with an empty prefix, matching
the internal sigGen oracle path.

A valid signature returns `testPassed=true`. A well-formed but invalid
signature, message, or mu returns `testPassed=false` with HTTP 200. Invalid
caller input returns HTTP 400, and native configuration, execution, or
malformed native output errors return HTTP 500.

```bash
cd backend/native/mldsa_oracle
SEED=000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F
MESSAGE=00010203040506070809

./bin/mldsa44_keygen_oracle "$SEED" > /tmp/keygen44.json
PK=$(python3 - <<'PY'
import json
print(json.load(open("/tmp/keygen44.json"))["pk"])
PY
)
SK=$(python3 - <<'PY'
import json
print(json.load(open("/tmp/keygen44.json"))["sk"])
PY
)

./bin/mldsa44_siggen_oracle "$SK" "$MESSAGE" > /tmp/siggen44.json
SIG=$(python3 - <<'PY'
import json
print(json.load(open("/tmp/siggen44.json"))["signature"])
PY
)

./bin/mldsa44_sigver_oracle "$PK" "$MESSAGE" "$SIG"
```

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/sigver \
  -H "Content-Type: application/json" \
  -d "{
    \"parameterSet\": \"ML-DSA-44\",
    \"signatureInterface\": \"external\",
    \"pk\": \"$PK\",
    \"message\": \"00010203040506070809\",
    \"signature\": \"$SIG\",
    \"preHash\": \"pure\",
    \"context\": \"\"
  }"
```

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/sigver \
  -H "Content-Type: application/json" \
  -d "{
    \"parameterSet\": \"ML-DSA-44\",
    \"signatureInterface\": \"internal\",
    \"externalMu\": false,
    \"pk\": \"$PK\",
    \"message\": \"00010203040506070809\",
    \"signature\": \"$SIG\"
  }"
```

## Start the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Call the single-case keyGen endpoint

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/keygen \
  -H "Content-Type: application/json" \
  -d '{
    "parameterSet": "ML-DSA-44",
    "seed": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
  }'
```

## Generate keyGen expectedResults

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/keygen/expected-results \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": {
      "vsId": 42,
      "algorithm": "ML-DSA",
      "mode": "keyGen",
      "revision": "FIPS204",
      "testGroups": [
        {
          "tgId": 1,
          "testType": "AFT",
          "parameterSet": "ML-DSA-44",
          "tests": [
            {
              "tcId": 1,
              "seed": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
            }
          ]
        }
      ]
    }
  }'
```

The generated `expectedResults` preserves `vsId`, `algorithm`, `mode`, `revision`, `tgId`, and `tcId`, and includes `pk` and `sk`. It does not copy prompt `seed` values into response test cases.

## Generate generic ML-DSA expectedResults

`POST /api/oracle/mldsa/expected-results` accepts either a direct ML-DSA
vector set object or an ACVP array container:

```json
[
  {"acvVersion": "1.0"},
  {
    "vsId": 42,
    "algorithm": "ML-DSA",
    "mode": "keyGen",
    "revision": "FIPS204",
    "testGroups": [
      {
        "tgId": 1,
        "testType": "AFT",
        "parameterSet": "ML-DSA-44",
        "tests": [
          {
            "tcId": 1,
            "seed": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
          }
        ]
      }
    ]
  }
]
```

The output preserves the input container style. Direct vector set input returns
a direct vector set. Array container input returns the version object followed
by the generated `expectedResults` vector set.

Supported modes:

```text
keyGen -> tcId, pk, sk
sigGen -> tcId, signature
sigVer -> tcId, testPassed
```

Prompt-only fields are intentionally not copied into the response:

```text
group: testType, parameterSet, deterministic, signatureInterface, externalMu, preHash
test: seed, sk, pk, message, mu, rnd, context, hashAlg, signature
```

Each output group contains only `tgId` and `tests`. If the prompt vector set
has top-level `isSample`, the generated vector set preserves it.

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/expected-results \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": {
      "vsId": 7001,
      "algorithm": "ML-DSA",
      "mode": "sigGen",
      "revision": "FIPS204",
      "testGroups": [
        {
          "tgId": 1,
          "testType": "AFT",
          "parameterSet": "ML-DSA-44",
          "signatureInterface": "internal",
          "externalMu": false,
          "deterministic": true,
          "tests": [
            {
              "tcId": 1,
              "sk": "PUT_SECRET_KEY_HEX_HERE",
              "message": "00010203040506070809"
            }
          ]
        }
      ]
    }
  }'
```

## Phase 2-2 oracle module refactor

The ML-DSA oracle wrapper is split into focused modules:

- `app.crypto_oracle.mldsa_errors` centralizes oracle exception classes.
- `app.crypto_oracle.mldsa_constants` centralizes parameter set metadata and native binary paths.
- `app.crypto_oracle.mldsa_helpers` centralizes hex validation, parameter-set validation, native subprocess execution, JSON parsing, and native output validation.
- `app.crypto_oracle.mldsa_oracle` keeps the public oracle API and compatibility re-exports.

After Phase 2-2, `keygen_internal()` remained the only implemented ML-DSA oracle operation and `siggen_internal()` / `sigver_internal()` were stubs. Phase 2-3 implements the restricted internal deterministic `siggen_internal()` path. Phase 2-4 implements the restricted internal `sigver_internal()` path. Phase 2-5 extends sigGen and sigVer to cover internal randomized and `externalMu=true` cases without adding expectedResults generation.

Generated keyGen `expectedResults` preserve prompt top-level `isSample` metadata when present, but still do not copy prompt group fields such as `parameterSet` or `testType`, and do not copy test case `seed` values.

## Phase 2-3 sigGen internal deterministic oracle

`siggen_internal()` is now implemented for one ACVP case shape: internal signature interface, `externalMu=false`, and deterministic signing. The native wrappers are:

- `bin/mldsa44_siggen_oracle`
- `bin/mldsa65_siggen_oracle`
- `bin/mldsa87_siggen_oracle`

Phase 2-5 extends this endpoint while preserving the old deterministic message
path and CLI.

## Phase 2-4 sigVer internal oracle

`sigver_internal()` is now implemented for one ACVP case shape: internal
signature interface and `externalMu=false`. The native wrappers are:

- `bin/mldsa44_sigver_oracle`
- `bin/mldsa65_sigver_oracle`
- `bin/mldsa87_sigver_oracle`

The API endpoint is `POST /api/oracle/mldsa/sigver`. It returns
`testPassed=true` for valid signatures and `testPassed=false` for well-formed
invalid signatures or messages. It does not generate sigVer `expectedResults`.

Phase 2-5 extends this endpoint while preserving the old message verify path
and CLI.

## Phase 2-5 internal randomized and externalMu coverage

sigGen support matrix:

```text
internal externalMu=false deterministic=true
internal externalMu=false deterministic=false
internal externalMu=true  deterministic=true
internal externalMu=true  deterministic=false
```

sigVer support matrix:

```text
internal externalMu=false
internal externalMu=true
```

For `deterministic=false`, requests must provide ACVP-controlled `rnd` of 32
bytes. The server does not call operating-system randomness. For
`externalMu=true`, requests must provide `mu` of 64 bytes and must not provide
`message`.

The native sigGen CLI preserves the old form:

```bash
./bin/mldsa44_siggen_oracle "$SK" "$MESSAGE"
```

It also supports:

```bash
./bin/mldsa44_siggen_oracle 0 1 "$SK" "$MESSAGE"
./bin/mldsa44_siggen_oracle 0 0 "$SK" "$MESSAGE" "$RND"
./bin/mldsa44_siggen_oracle 1 1 "$SK" "$MU"
./bin/mldsa44_siggen_oracle 1 0 "$SK" "$MU" "$RND"
```

The native sigVer CLI preserves the old form:

```bash
./bin/mldsa44_sigver_oracle "$PK" "$MESSAGE" "$SIG"
```

It also supports:

```bash
./bin/mldsa44_sigver_oracle 0 "$PK" "$MESSAGE" "$SIG"
./bin/mldsa44_sigver_oracle 1 "$PK" "$MU" "$SIG"
```

Full ACVP lifecycle endpoints remain out of scope.

## Phase 2-6 external pure and preHash coverage

sigGen external CLI:

```bash
./bin/mldsa44_siggen_oracle external pure 1 "$SK" "$MESSAGE" "$CTX"
./bin/mldsa44_siggen_oracle external pure 0 "$SK" "$MESSAGE" "$CTX" "$RND"
./bin/mldsa44_siggen_oracle external preHash 1 "$SK" "$PH" "$CTX" SHA2-256
./bin/mldsa44_siggen_oracle external preHash 0 "$SK" "$PH" "$CTX" SHA2-256 "$RND"
```

sigVer external CLI:

```bash
./bin/mldsa44_sigver_oracle external pure "$PK" "$MESSAGE" "$CTX" "$SIG"
./bin/mldsa44_sigver_oracle external preHash "$PK" "$PH" "$CTX" SHA2-256 "$SIG"
```

`CTX` is a hex string whose decoded length must be 0 to 255 bytes. For
external pure, the native wrapper prepares the FIPS 204 domain-separation
prefix with `MLD_PREHASH_NONE` and calls `mldsa_signature_internal()` /
`mldsa_verify_internal()` with `externalmu=0`. For external preHash, Python
hashes the message first and the native wrapper calls
`mldsa_signature_pre_hash_internal()` / `mldsa_verify_pre_hash_internal()`.

Supported Python/API `hashAlg` values are:

```text
SHA2-224
SHA2-256
SHA2-384
SHA2-512
SHA2-512/224
SHA2-512/256
SHA3-224
SHA3-256
SHA3-384
SHA3-512
SHAKE-128
SHAKE-256
```

Phase 5-2 maps `SHAKE-128` to a 32-byte prehash and `SHAKE-256` to a 64-byte
prehash. This matches the native CLI `parse_hash_alg()` mapping and allows
Python/API expectedResults generation to cover SHAKE external preHash cases.

## Phase 2-7 generic expectedResults coverage

The generic endpoint dispatches by prompt `mode`:

```text
POST /api/oracle/mldsa/expected-results
```

Supported sigGen combinations:

```text
internal externalMu=false deterministic=true
internal externalMu=false deterministic=false
internal externalMu=true  deterministic=true
internal externalMu=true  deterministic=false
external pure             deterministic=true
external pure             deterministic=false
external preHash          deterministic=true
external preHash          deterministic=false
```

Supported sigVer combinations:

```text
internal externalMu=false
internal externalMu=true
external pure
external preHash
```

The existing keyGen-only endpoint remains available:

```text
POST /api/oracle/mldsa/keygen/expected-results
```

Phase 5-2 generic sigGen/sigVer external preHash supports SHA2, SHA3,
`SHAKE-128`, and `SHAKE-256`.

## Phase 2-8 generated import pipeline

The generated import endpoint accepts `prompt + response`, generates
expectedResults from the prompt, validates both expectedResults and response
schemas, stores the import bundle, and returns the existing `ImportSummary`.

```text
POST /api/import/generated
POST /api/import/generated-and-validate
```

`generated-and-validate` additionally runs validation and builds a report in
one call. The existing keyGen-only endpoint remains available:

```text
POST /api/import/generated-keygen
```

Validation summaries include `extra` response cases in addition to `passed`,
`failed`, `missing`, and `malformed`. Report markdown includes the same extra
count.

## Phase 2-9 local demo lifecycle

The local demo lifecycle uses `/api/demo/acvp`, not official `/acvp/v1`.

```text
POST   /api/demo/acvp/test-sessions
GET    /api/demo/acvp/test-sessions
GET    /api/demo/acvp/test-sessions/{sessionId}
GET    /api/demo/acvp/test-sessions/{sessionId}/vector-set
POST   /api/demo/acvp/test-sessions/{sessionId}/responses
GET    /api/demo/acvp/test-sessions/{sessionId}/validation
GET    /api/demo/acvp/test-sessions/{sessionId}/report
DELETE /api/demo/acvp/test-sessions/{sessionId}
```

Responses are marked with `demoOnly=true` and `notProductionAcvp=true`. This
is a PostgreSQL-backed local demo, not a production ACVP server.

## Current non-goals

The backend does not currently include:

- Production registration negotiation
- Production database deployment
- JWT authentication
- Production ACVP vector set lifecycle
- Certificate workflow
