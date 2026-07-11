# NCCU ACVP Server Backend

FastAPI backend for NCCU ACVP Server and its FIPS 204 / ML-DSA local validator.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## ML-DSA oracle

This backend includes local crypto oracle integration for ML-DSA keyGen,
sigGen, sigVer, and expectedResults generation using the external
`mldsa-native` checkout at `/root/ACVP204/mldsa-native`.

Build the native oracle binaries:

```bash
cd backend/native/mldsa_oracle
make clean
make
```

Test the C oracle directly:

```bash
./bin/mldsa44_keygen_oracle 000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F
```

Start the backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Test the FastAPI oracle endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/oracle/mldsa/keygen \
  -H "Content-Type: application/json" \
  -d '{
    "parameterSet": "ML-DSA-44",
    "seed": "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
  }'
```

The response includes `pk` and `sk` as uppercase hex strings.

Current scope:

- This is only a crypto oracle integration, not a formal ACVP
  session/vector set lifecycle implementation.
- Single-case ML-DSA keyGen, sigGen, and sigVer endpoints are supported.
- `POST /api/oracle/mldsa/expected-results` generates keyGen, sigGen, and
  sigVer expectedResults for validated ML-DSA prompt vector sets.
- `POST /api/import/generated` and
  `POST /api/import/generated-and-validate` support generated expectedResults
  import and validation flows for keyGen, sigGen, and sigVer.
- `/api/demo/acvp/test-sessions` provides an in-memory local demo lifecycle.
  It is marked as demo-only and is not the official ACVP production protocol.
