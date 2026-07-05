#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENDOR_ROOT="${REPO_ROOT}/third_party/nist-acvp-server"
BIN_ROOT="${REPO_ROOT}/.nist-bin"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet SDK not found. Install .NET 8 SDK before building NIST GenValAppRunner." >&2
  exit 1
fi

if [[ ! -d "${VENDOR_ROOT}/_config" || ! -d "${VENDOR_ROOT}/gen-val" ]]; then
  echo "NIST Gen/Val vendor directory is missing. Run scripts/nist/copy_nist_genval.sh first." >&2
  exit 1
fi

cp "${VENDOR_ROOT}/_config/Directory.Build.props" "${VENDOR_ROOT}/Directory.Build.props"
cp "${VENDOR_ROOT}/_config/Directory.Packages.props" "${VENDOR_ROOT}/Directory.Packages.props"

runner_csproj="${VENDOR_ROOT}/gen-val/samples/GenValAppRunner/src/NIST.CVP.ACVTS.Generation.GenValApp.csproj"
orleans_csproj="${VENDOR_ROOT}/gen-val/samples/NIST.CVP.ACVTS.Orleans.ServerHost/NIST.CVP.ACVTS.Orleans.ServerHost.csproj"

if [[ ! -f "${runner_csproj}" ]]; then
  runner_csproj="$(find "${VENDOR_ROOT}/gen-val" -name '*GenValApp*.csproj' | head -n 1)"
fi
if [[ ! -f "${orleans_csproj}" ]]; then
  orleans_csproj="$(find "${VENDOR_ROOT}/gen-val" -name '*Orleans.ServerHost*.csproj' | head -n 1)"
fi

if [[ -z "${runner_csproj}" || ! -f "${runner_csproj}" ]]; then
  echo "Could not find GenValAppRunner csproj under ${VENDOR_ROOT}/gen-val" >&2
  exit 1
fi
if [[ -z "${orleans_csproj}" || ! -f "${orleans_csproj}" ]]; then
  echo "Could not find Orleans.ServerHost csproj under ${VENDOR_ROOT}/gen-val" >&2
  exit 1
fi

mkdir -p "${BIN_ROOT}/genval-runner" "${BIN_ROOT}/orleans-server"

dotnet publish "${runner_csproj}" \
  -c Release \
  -o "${BIN_ROOT}/genval-runner"

dotnet publish "${orleans_csproj}" \
  -c Release \
  -o "${BIN_ROOT}/orleans-server"

echo "Published GenValAppRunner to ${BIN_ROOT}/genval-runner"
echo "Published Orleans.ServerHost to ${BIN_ROOT}/orleans-server"
