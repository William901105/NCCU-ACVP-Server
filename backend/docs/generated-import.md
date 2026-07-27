# Generated ML-DSA Import Pipeline

Phase 2-8 adds generated import endpoints that reuse the generic ML-DSA
expectedResults generator.

This is still a local validation demo. It is not an ACVP production lifecycle,
does not implement `/acvp/v1/testSessions`, and does not add registration
negotiation, JWT, certificates, or production ACVP authentication. Phase 4-1
stores imported/generated bundles, validation results, and reports in PostgreSQL.

## Endpoints

```text
POST /api/import/generated
POST /api/import/generated-and-validate
```

`POST /api/import/generated` accepts:

```json
{
  "prompt": {},
  "response": {},
  "label": "optional label"
}
```

The backend:

1. Validates the prompt as an ML-DSA vector set.
2. Generates expectedResults with `generate_expected_results_from_prompt()`.
3. Validates the generated expectedResults schema.
4. Validates the submitted response schema for the prompt mode.
5. Stores the bundle in PostgreSQL with `generatedExpectedResults: true`.
6. Returns the normal `ImportSummary`.

`POST /api/import/generated-and-validate` runs the same import path, immediately
executes validation, stores the validation result and report in PostgreSQL, and returns:

```json
{
  "import": {},
  "validationResult": {},
  "report": {}
}
```

The existing keyGen-only endpoint remains available:

```text
POST /api/import/generated-keygen
```

## Supported Modes

```text
keyGen
sigGen
sigVer
```

The generated expectedResults response test case shapes remain ACVP response
shapes:

```text
keyGen -> tcId, pk, sk
sigGen -> tcId, signature
sigVer -> tcId, testPassed
```

Prompt-only fields such as `testType`, `parameterSet`, `deterministic`,
`signatureInterface`, `externalMu`, `preHash`, `seed`, `sk`, `pk`, `message`,
`mu`, `rnd`, `context`, `hashAlg`, and prompt `signature` are not copied into
generated expectedResults.

## Validator Summary

Validation summary now includes `extra` response cases:

```json
{
  "total": 1,
  "passed": 1,
  "failed": 0,
  "missing": 0,
  "malformed": 0,
  "extra": 0
}
```

The report markdown includes the same `extra` count. Extra response cases also
appear in `failureDetails` with reason `extra response test case`.

## Manual Check

```bash
cd NCCU-ACVP-Server/backend
source .venv/bin/activate
DATABASE_URL=postgresql://acvp_app:<password>@127.0.0.1:5432/acvp \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then post a prompt/response pair:

```bash
curl -s -X POST http://127.0.0.1:8000/api/import/generated-and-validate \
  -H "Content-Type: application/json" \
  -d @/tmp/generated-import-request.json
```

The response should include `import`, `validationResult`, and `report`.
Restarting the backend with the same `DATABASE_URL` should preserve
`GET /api/import/{importId}` and `GET /api/report/{importId}`.
