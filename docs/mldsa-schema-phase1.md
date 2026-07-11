# ML-DSA Schema Phase 1

This phase adds a backend schema validation layer for ML-DSA ACVP JSON.
It is aligned with NIST ACVP ML-DSA draft-celi-acvp-ml-dsa-01:

<https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html>

## Scope

Supported algorithm/mode/revision combinations:

- ML-DSA / keyGen / FIPS204
- ML-DSA / sigGen / FIPS204
- ML-DSA / sigVer / FIPS204

The backend validates registration, prompt/test vector set, and response
schema. It returns structured schema errors with JSON paths.

## Not Supported

- Formal ACVP session or vector set lifecycle
- Vector generation
- expectedResults generation
- sigGen/sigVer/keyGen cryptographic validation
- JWT, login, vendor, module, or OE management

## API

Validate a registration:

```bash
curl -X POST http://127.0.0.1:8000/api/schema/mldsa/registration \
  -H "Content-Type: application/json" \
  -d @registration.json
```

Validate a prompt/test vector set:

```bash
curl -X POST http://127.0.0.1:8000/api/schema/mldsa/vector-set \
  -H "Content-Type: application/json" \
  -d @prompt.json
```

Validate a response:

```bash
curl -X POST http://127.0.0.1:8000/api/schema/mldsa/response \
  -H "Content-Type: application/json" \
  -d @response.json
```

Success response:

```json
{
  "ok": true,
  "type": "vector-set",
  "normalized": {}
}
```

Schema error response:

```json
{
  "ok": false,
  "errorType": "schema",
  "code": "missing_required_field",
  "path": "$.testGroups[0].tests[3].seed",
  "message": "Missing required field: seed"
}
```

## Import Flow

`POST /api/import` now validates:

- `prompt` with the vector set schema
- `expectedResults` with the response schema
- `response` with the response schema

The existing sample import, validate, and report workflow remains in place.

## Testing

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Sample Data Notes

The current ML-DSA sample prompt, expectedResults, response.pass, and
response.fail files validate against this Phase 1 schema layer. No sample-data
schema mismatch was found during implementation.

This phase does not claim formal NIST production ACVP compliance.
