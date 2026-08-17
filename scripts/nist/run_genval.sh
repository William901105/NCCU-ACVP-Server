#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/nist/run_genval.sh check path/to/registration.json
  scripts/nist/run_genval.sh generate path/to/registration.json
  scripts/nist/run_genval.sh validate path/to/internalProjection.json path/to/response.json
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNNER_DLL="${REPO_ROOT}/.nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet runtime not found. Install .NET 8 before running GenValAppRunner." >&2
  exit 1
fi

if [[ ! -f "${RUNNER_DLL}" ]]; then
  echo "GenValAppRunner binary not found at ${RUNNER_DLL}" >&2
  echo "Run scripts/nist/build_nist_genval.sh first." >&2
  exit 1
fi

mode="${1:-}"
case "${mode}" in
  check)
    [[ $# -eq 2 ]] || { usage; exit 2; }
    exec dotnet "${RUNNER_DLL}" -c "$2"
    ;;
  generate)
    [[ $# -eq 2 ]] || { usage; exit 2; }
    exec dotnet "${RUNNER_DLL}" -g "$2"
    ;;
  validate)
    [[ $# -eq 3 ]] || { usage; exit 2; }
    exec dotnet "${RUNNER_DLL}" -n "$2" -b "$3"
    ;;
  *)
    usage
    exit 2
    ;;
esac
