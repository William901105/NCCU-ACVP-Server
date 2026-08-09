#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_ROOT="${1:-${REPO_ROOT}/../ACVP-Server}"
TARGET_ROOT="${REPO_ROOT}/third_party/nist-acvp-server"
PINNED_COMMIT="a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324"
PINNED_TAG="v1.1.0.43"
PINNED_DESCRIPTION="v1.1.0.43-4-ga7f283cd"
SOURCE_REPOSITORY="https://github.com/usnistgov/ACVP-Server"
PATCH_FILE="${SCRIPT_DIR}/patches/a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch"
PATCH_SHA256="d421d216a21d0ea38a596342dee6a4144598f33fd40b7b58d4a5916203573ade"

if [[ ! -d "${SOURCE_ROOT}" ]]; then
  echo "NIST ACVP-Server checkout not found: ${SOURCE_ROOT}" >&2
  exit 1
fi

if [[ ! -d "${SOURCE_ROOT}/_config" || ! -d "${SOURCE_ROOT}/gen-val" ]]; then
  echo "Expected _config/ and gen-val/ under ${SOURCE_ROOT}" >&2
  exit 1
fi

source_commit="$(git -C "${SOURCE_ROOT}" rev-parse HEAD 2>/dev/null || true)"
if [[ "${source_commit}" != "${PINNED_COMMIT}" ]]; then
  echo "NIST ACVP-Server source must be checked out at ${PINNED_COMMIT}; found ${source_commit:-unknown}." >&2
  exit 1
fi

if [[ ! -f "${PATCH_FILE}" ]]; then
  echo "Required local NIST compatibility patch is missing: ${PATCH_FILE}" >&2
  exit 1
fi
actual_patch_sha256="$(sha256sum "${PATCH_FILE}" | awk '{print $1}')"
if [[ "${actual_patch_sha256}" != "${PATCH_SHA256}" ]]; then
  echo "Local NIST compatibility patch hash mismatch: expected ${PATCH_SHA256}, found ${actual_patch_sha256}." >&2
  exit 1
fi

mkdir -p "${TARGET_ROOT}"

rsync -a --delete \
  --exclude ".git/" \
  --exclude "bin/" \
  --exclude "obj/" \
  "${SOURCE_ROOT}/_config/" "${TARGET_ROOT}/_config/"

mkdir -p "${TARGET_ROOT}/gen-val"
rsync -a --delete \
  --exclude ".git/" \
  --exclude "bin/" \
  --exclude "obj/" \
  --exclude "/json-files/*" \
  "${SOURCE_ROOT}/gen-val/" "${TARGET_ROOT}/gen-val/"

mkdir -p "${TARGET_ROOT}/gen-val/json-files"
for name in \
  ML-KEM-keyGen-FIPS203 \
  ML-KEM-encapDecap-FIPS203 \
  ML-KEM-encapDecap-FIPS203-tr1 \
  ML-DSA-keyGen-FIPS204 \
  ML-DSA-sigGen-FIPS204 \
  ML-DSA-sigGen-FIPS204-tr1 \
  ML-DSA-sigVer-FIPS204
do
  if [[ -d "${SOURCE_ROOT}/gen-val/json-files/${name}" ]]; then
    rsync -a --delete \
      --exclude ".git/" \
      --exclude "bin/" \
      --exclude "obj/" \
      "${SOURCE_ROOT}/gen-val/json-files/${name}/" \
      "${TARGET_ROOT}/gen-val/json-files/${name}/"
  else
    echo "Required NIST GenVal json-files directory is missing: ${name}" >&2
    exit 1
  fi
done

if [[ -f "${SOURCE_ROOT}/README.md" ]]; then
  cp "${SOURCE_ROOT}/README.md" "${TARGET_ROOT}/NIST_README.md"
fi

git -C "${REPO_ROOT}" apply --check --ignore-whitespace \
  --directory="third_party/nist-acvp-server" "${PATCH_FILE}"
git -C "${REPO_ROOT}" apply --ignore-whitespace \
  --directory="third_party/nist-acvp-server" "${PATCH_FILE}"

copied_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "${TARGET_ROOT}/NIST_SOURCE.md" <<EOF
# NIST ACVP-Server Source

- source repository: ${SOURCE_REPOSITORY}
- source git commit: ${source_commit}
- upstream release/tag: ${PINNED_TAG}
- source git describe: ${PINNED_DESCRIPTION}
- copied timestamp: ${copied_at}
- selection reason: latest official master commit as of 2026-08-09; includes v1.1.0.43 tr1 support and the post-release official fixture corrections.
- local patch: scripts/nist/patches/a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch
- local patch sha256: ${PATCH_SHA256}
- local patch purpose: set FIPS203-tr1 decapsulationKeyCheck test-group KeyFormat to Expanded so prompt projection includes dk.
- integration note: NIST code is copied into this repository; it is not a git submodule.

This directory vendors the NIST ACVP-Server Gen/Val code needed by the NCCU
ACVP Server integration. Re-run scripts/nist/copy_nist_genval.sh to refresh it
from a local NIST ACVP-Server checkout.

This is not an unmodified official NIST GenVal source tree. It is the exact
official source commit above plus the single local compatibility patch recorded
in NIST_PATCHES.md.
EOF

echo "Copied NIST Gen/Val code to ${TARGET_ROOT}"
