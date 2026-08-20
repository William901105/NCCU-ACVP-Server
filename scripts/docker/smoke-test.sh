#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${ACVP_BASE_URL:-http://127.0.0.1:${ACVP_HTTP_PORT:-8080}}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

curl --fail --silent --show-error "${BASE_URL}/healthz" > "${WORK_DIR}/frontend-health.json"
curl --fail --silent --show-error "${BASE_URL}/api/health" > "${WORK_DIR}/engine-health.json"
curl --fail --silent --show-error \
    --request POST \
    "${BASE_URL}/acvp/v1/accessTokens" > "${WORK_DIR}/token.json"

TOKEN="$(python3 -c 'import json,sys; payload=json.load(sys.stdin); body=payload[1] if isinstance(payload,list) else payload; print(body["accessToken"])' < "${WORK_DIR}/token.json")"

curl --fail --silent --show-error \
    --header "Authorization: Bearer ${TOKEN}" \
    "${BASE_URL}/acvp/v1/version" > "${WORK_DIR}/version.json"
curl --fail --silent --show-error \
    --header "Authorization: Bearer ${TOKEN}" \
    "${BASE_URL}/acvp/v1/algorithms" > "${WORK_DIR}/algorithms.json"

python3 - "${WORK_DIR}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
frontend = json.loads((root / "frontend-health.json").read_text())
engine = json.loads((root / "engine-health.json").read_text())
algorithms_payload = json.loads((root / "algorithms.json").read_text())
algorithms_body = algorithms_payload[1] if isinstance(algorithms_payload, list) else algorithms_payload
algorithms = algorithms_body.get("algorithms", [])
names = {item.get("algorithm") for item in algorithms}

assert frontend == {"status": "ok"}, frontend
assert engine == {"status": "ok"}, engine
assert {"ML-DSA", "ML-KEM"}.issubset(names), names
print("Smoke test passed: frontend, engine, token authentication, ML-DSA, and ML-KEM discovery.")
PY
