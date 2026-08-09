#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENDOR_ROOT="${REPO_ROOT}/third_party/nist-acvp-server"
BIN_ROOT="${REPO_ROOT}/.nist-bin"
PINNED_COMMIT="a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324"
SOURCE_MANIFEST="${VENDOR_ROOT}/NIST_SOURCE.md"
PATCH_FILE="${REPO_ROOT}/scripts/nist/patches/a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch"
PATCH_SHA256="d421d216a21d0ea38a596342dee6a4144598f33fd40b7b58d4a5916203573ade"
PATCHED_SOURCE="${VENDOR_ROOT}/gen-val/src/generation/src/NIST.CVP.ACVTS.Libraries.Generation/ML-KEM/FIPS203/tr1/EncapDecap/TestGroupGeneratorKeyCheckVal.cs"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet SDK not found. Install .NET 8 SDK before building NIST GenValAppRunner." >&2
  exit 1
fi

if [[ ! -d "${VENDOR_ROOT}/_config" || ! -d "${VENDOR_ROOT}/gen-val" ]]; then
  echo "NIST Gen/Val vendor directory is missing. Run scripts/nist/copy_nist_genval.sh first." >&2
  exit 1
fi

if [[ ! -f "${SOURCE_MANIFEST}" ]] || ! rg -q "source git commit: ${PINNED_COMMIT}" "${SOURCE_MANIFEST}"; then
  echo "Vendored NIST source is not the required pinned commit ${PINNED_COMMIT}." >&2
  exit 1
fi
if [[ ! -f "${PATCH_FILE}" ]] || [[ "$(sha256sum "${PATCH_FILE}" | awk '{print $1}')" != "${PATCH_SHA256}" ]]; then
  echo "Required local NIST compatibility patch is missing or has the wrong hash." >&2
  exit 1
fi
if [[ ! -f "${PATCHED_SOURCE}" ]] || ! rg -q 'KeyFormat = PrivateKeyFormat\.Expanded,' "${PATCHED_SOURCE}"; then
  echo "Vendored NIST source does not contain the required ML-KEM tr1 compatibility patch." >&2
  exit 1
fi
if ! rg -q "local patch sha256: ${PATCH_SHA256}" "${SOURCE_MANIFEST}"; then
  echo "NIST source manifest does not record the required local patch." >&2
  exit 1
fi
echo "Building NIST ACVP-Server base ${PINNED_COMMIT} plus documented local ML-KEM tr1 patch ${PATCH_SHA256}"

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
  -m:1 \
  -c Release \
  -o "${BIN_ROOT}/genval-runner"

dotnet publish "${orleans_csproj}" \
  -m:1 \
  -c Release \
  -o "${BIN_ROOT}/orleans-server"

echo "Published GenValAppRunner to ${BIN_ROOT}/genval-runner"
echo "Published Orleans.ServerHost to ${BIN_ROOT}/orleans-server"
