#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FIXTURE_ROOT="${REPO_ROOT}/tests/fixtures/nist/mldsa"
VENDOR_ROOT="${REPO_ROOT}/third_party/nist-acvp-server"
RUN_GENVAL="${REPO_ROOT}/scripts/nist/run_genval.sh"
START_ORLEANS="${REPO_ROOT}/scripts/nist/start_orleans.sh"
IUT_RUNNER="${REPO_ROOT}/IUT-tests/mldsa-native/run_test.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$(pwd -P)" != "${REPO_ROOT}" ]]; then
  echo "Run this script from the repository root: ${REPO_ROOT}" >&2
  exit 1
fi

for command in dotnet git "${PYTHON_BIN}"; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command is missing: ${command}" >&2
    exit 1
  fi
done

runner_dll="${REPO_ROOT}/.nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll"
orleans_dll="${REPO_ROOT}/.nist-bin/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll"
for required_path in \
  "${VENDOR_ROOT}/_config" \
  "${VENDOR_ROOT}/gen-val" \
  "${VENDOR_ROOT}/NIST_SOURCE.md" \
  "${runner_dll}" \
  "${orleans_dll}" \
  "${RUN_GENVAL}" \
  "${START_ORLEANS}" \
  "${IUT_RUNNER}"; do
  if [[ ! -e "${required_path}" ]]; then
    echo "Required NIST artifact is missing: ${required_path}" >&2
    exit 1
  fi
done

nist_source_commit="$(awk -F': ' '/^- source git commit: / {print $2; exit}' "${VENDOR_ROOT}/NIST_SOURCE.md")"
if [[ -z "${nist_source_commit}" || "${nist_source_commit}" == "unknown" ]]; then
  echo "NIST source commit is missing from ${VENDOR_ROOT}/NIST_SOURCE.md" >&2
  exit 1
fi

baseline_commit="$(git rev-list -n 1 pre-strict-refactor^{})"
if [[ -z "${baseline_commit}" ]]; then
  echo "Annotated tag pre-strict-refactor is required before capturing fixtures." >&2
  exit 1
fi

staging_root="$(mktemp -d "${REPO_ROOT}/.strict-baseline.XXXXXX")"
orleans_pid=""

cleanup() {
  if [[ -n "${orleans_pid}" ]] && kill -0 "${orleans_pid}" >/dev/null 2>&1; then
    kill "${orleans_pid}" >/dev/null 2>&1 || true
    wait "${orleans_pid}" >/dev/null 2>&1 || true
  fi
  rm -rf "${staging_root}"
}
trap cleanup EXIT INT TERM

port_open() {
  local port="$1"
  (echo >/dev/tcp/127.0.0.1/"${port}") >/dev/null 2>&1
}

orleans_ready() {
  port_open 11111 && port_open 30000
}

if ! orleans_ready; then
  echo "Starting Orleans.ServerHost for NIST fixture capture..."
  "${START_ORLEANS}" \
    >"${staging_root}/orleans.stdout.txt" \
    2>"${staging_root}/orleans.stderr.txt" &
  orleans_pid=$!
  ready=0
  for _ in $(seq 1 60); do
    if kill -0 "${orleans_pid}" >/dev/null 2>&1 && orleans_ready; then
      ready=1
      break
    fi
    sleep 1
  done
  if [[ "${ready}" != 1 ]]; then
    echo "Orleans.ServerHost did not become available on ports 11111 and 30000." >&2
    sed -n '1,120p' "${staging_root}/orleans.stderr.txt" >&2 || true
    exit 1
  fi
else
  echo "Using the already available Orleans.ServerHost on ports 11111 and 30000."
fi

capture_timestamp="${CAPTURE_TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
mkdir -p "${staging_root}/mldsa"

for mode in keyGen sigGen sigVer; do
  nist_name="ML-DSA-${mode}-FIPS204"
  source_dir="${VENDOR_ROOT}/gen-val/json-files/${nist_name}"
  mode_dir="${staging_root}/mldsa/${mode}"
  mkdir -p "${mode_dir}"

  for source_file in registration.json; do
    if [[ ! -f "${source_dir}/${source_file}" ]]; then
      echo "Missing NIST registration: ${source_dir}/${source_file}" >&2
      exit 1
    fi
  done
  cp "${source_dir}/registration.json" "${mode_dir}/registration.json"
  "${PYTHON_BIN}" - "${mode_dir}/registration.json" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
PY
  "${RUN_GENVAL}" check "${mode_dir}/registration.json" \
    >"${mode_dir}/check.stdout.txt" \
    2>"${mode_dir}/check.stderr.txt"
  "${RUN_GENVAL}" generate "${mode_dir}/registration.json" \
    >"${mode_dir}/generate.stdout.txt" \
    2>"${mode_dir}/generate.stderr.txt"

  for generated_file in prompt.json internalProjection.json expectedResults.json; do
    if [[ ! -f "${mode_dir}/${generated_file}" ]]; then
      echo "GenVal did not produce ${generated_file} for ${mode}." >&2
      exit 1
    fi
  done

  mkdir -p "${mode_dir}/iut-response"
  "${PYTHON_BIN}" "${IUT_RUNNER}" \
    --prompt "${mode_dir}/prompt.json" \
    --response-dir "${mode_dir}/iut-response" \
    --variant both \
    --expect-mode "${mode}" \
    >"${mode_dir}/iut.stdout.txt" \
    2>"${mode_dir}/iut.stderr.txt"
  cp "${mode_dir}/iut-response/response_pass_${mode}.json" "${mode_dir}/response.pass.json"
  cp "${mode_dir}/iut-response/response_fail_${mode}.json" "${mode_dir}/response.fail.json"
  rm -rf "${mode_dir}/iut-response"
  rm -f "${mode_dir}/iut.stdout.txt" "${mode_dir}/iut.stderr.txt"

  for variant in pass fail; do
    validation_dir="${mode_dir}/validate-${variant}"
    mkdir -p "${validation_dir}"
    cp "${mode_dir}/internalProjection.json" "${validation_dir}/internalProjection.json"
    cp "${mode_dir}/response.${variant}.json" "${validation_dir}/response.json"

    set +e
    (
      cd "${validation_dir}"
      "${RUN_GENVAL}" validate internalProjection.json response.json \
        >"../validate-${variant}.stdout.txt" \
        2>"../validate-${variant}.stderr.txt"
    )
    validate_status=$?
    set -e

    if [[ ! -f "${validation_dir}/validation.json" ]]; then
      echo "GenVal did not produce validation.json for ${mode} ${variant}." >&2
      exit 1
    fi
    if [[ "${variant}" == pass && "${validate_status}" != 0 ]]; then
      echo "NIST pass validation failed for ${mode} with exit code ${validate_status}." >&2
      exit 1
    fi
    if [[ "${variant}" == fail && "${validate_status}" == 0 ]]; then
      echo "NIST fail validation unexpectedly returned success for ${mode}." >&2
      exit 1
    fi
    cp "${validation_dir}/validation.json" "${mode_dir}/validation.${variant}.json"
  done

  rm -rf "${mode_dir}/validate-pass" "${mode_dir}/validate-fail"

  "${PYTHON_BIN}" - "${mode_dir}" "${mode}" "${nist_source_commit}" "${baseline_commit}" "${capture_timestamp}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

mode_dir = Path(sys.argv[1])
mode = sys.argv[2]
nist_source_commit = sys.argv[3]
baseline_commit = sys.argv[4]
capture_timestamp = sys.argv[5]

json_files = [
    "registration.json",
    "prompt.json",
    "internalProjection.json",
    "expectedResults.json",
    "response.pass.json",
    "response.fail.json",
    "validation.pass.json",
    "validation.fail.json",
]
text_files = [
    "Check.log",
    "Generate.log",
    "check.stdout.txt",
    "check.stderr.txt",
    "generate.stdout.txt",
    "generate.stderr.txt",
    "validate-pass.stdout.txt",
    "validate-pass.stderr.txt",
    "validate-fail.stdout.txt",
    "validate-fail.stderr.txt",
]

payloads = {}
for name in json_files:
    path = mode_dir / name
    if not path.exists():
        raise SystemExit(f"missing fixture file: {path}")
    payloads[name] = json.loads(path.read_text(encoding="utf-8"))

expected_groups = payloads["expectedResults.json"].get("testGroups")
pass_groups = payloads["response.pass.json"].get("testGroups")
fail_groups = payloads["response.fail.json"].get("testGroups")
if expected_groups != pass_groups:
    raise SystemExit(f"pass response test cases do not match NIST expected results for {mode}")
if expected_groups == fail_groups:
    raise SystemExit(f"fail response does not change a test case for {mode}")
if payloads["validation.pass.json"].get("disposition") != "passed":
    raise SystemExit(f"pass validation is not passed for {mode}")
if payloads["validation.fail.json"].get("disposition") != "failed":
    raise SystemExit(f"fail validation is not failed for {mode}")

for name in text_files:
    path = mode_dir / name
    if not path.exists():
        raise SystemExit(f"missing capture log: {path}")

repo_root = mode_dir.parents[2]
for path in mode_dir.iterdir():
    if path.is_file() and str(repo_root) in path.read_text(encoding="utf-8", errors="replace"):
        raise SystemExit(f"absolute repository path found in fixture: {path.name}")

files = {}
for name in json_files + text_files:
    files[name] = hashlib.sha256((mode_dir / name).read_bytes()).hexdigest()

manifest = {
    "mode": mode,
    "nistSourceCommit": nist_source_commit,
    "baselineApplicationCommit": baseline_commit,
    "captureCommand": "scripts/baseline/capture_strict_baseline.sh",
    "captureTimestamp": capture_timestamp,
    "files": files,
}
(mode_dir / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
done

mkdir -p "${REPO_ROOT}/tests/fixtures/nist"
backup_root="${REPO_ROOT}/.strict-baseline-fixtures.backup.$$"
if [[ -e "${FIXTURE_ROOT}" ]]; then
  mv "${FIXTURE_ROOT}" "${backup_root}"
fi
if ! mv "${staging_root}/mldsa" "${FIXTURE_ROOT}"; then
  if [[ -e "${backup_root}" ]]; then
    mv "${backup_root}" "${FIXTURE_ROOT}"
  fi
  exit 1
fi
rm -rf "${backup_root}"

echo "Captured verified NIST ML-DSA fixtures in tests/fixtures/nist/mldsa."
