#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER_DLL="${REPO_ROOT}/.nist-bin/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet runtime not found. Install .NET 8 before starting Orleans.ServerHost." >&2
  exit 1
fi

if [[ ! -f "${SERVER_DLL}" ]]; then
  echo "Orleans.ServerHost binary not found at ${SERVER_DLL}" >&2
  echo "Run scripts/nist/build_nist_genval.sh first." >&2
  exit 1
fi

exec dotnet "${SERVER_DLL}" --console
