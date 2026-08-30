# NCCU ACVP Server Backend

FastAPI backend for the strict FIPS 203 / ML-KEM and FIPS 204 / ML-DSA ACVP
workflow. PostgreSQL is the only runtime database, and the pinned NIST
ACVP-Server GenVal runtime is the only vector-generation and result-validation
backend.

The production HTTP surface is:

- `/api/health`
- `/acvp/v1/accessTokens`
- authenticated `/acvp/v1/*` protocol resources

The removed local oracle, import, sample-data, legacy `/api/report/*`, and demo
endpoint families are not part of the application. Completed strict ACVP test
sessions expose their authenticated validation evidence at
`/acvp/v1/testSessions/{sessionId}/reports` and as a downloadable PDF at the
corresponding `/reports/pdf` resource.

## Recommended startup

For manual or vendor acceptance, use the repository Docker deployment. It
starts FastAPI, NIST Orleans and PostgreSQL with the required paths and health
checks:

```bash
cd ..
./scripts/docker/start.sh
./scripts/docker/smoke-test.sh
```

See [`../DEPLOYMENT.md`](../DEPLOYMENT.md) for the one-time secret setup,
backup and shutdown procedures.

## Local development

Local development requires PostgreSQL plus a built NIST GenVal runner and a
running Orleans ServerHost. Build GenVal first, then keep Orleans running in a
separate terminal:

```bash
cd ..
./scripts/nist/build_nist_genval.sh
./scripts/nist/start_orleans.sh
```

In another terminal, start FastAPI:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL='postgresql://acvp_app:<password>@127.0.0.1:5432/acvp'
export ACVP_GENVAL_RUNNER_DLL='../.nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll'
export ACVP_GENVAL_ARTIFACT_ROOT='/tmp/nccu-acvp-genval'

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Tests

Tests must use a dedicated database named `acvp_test` unless
`ACVP_TEST_DATABASE_NAME` explicitly changes the reset guard:

```bash
source .venv/bin/activate
export ACVP_TEST_DATABASE_URL='postgresql://acvp_test_user:<password>@127.0.0.1:5432/acvp_test'
pytest -q
```

Database details are documented in
[`docs/persistence-postgresql.md`](docs/persistence-postgresql.md). The complete
system contract and supported algorithm identities are documented in the root
[`README.md`](../README.md).
