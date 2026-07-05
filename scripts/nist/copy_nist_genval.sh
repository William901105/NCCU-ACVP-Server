#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_ROOT="${1:-${REPO_ROOT}/../ACVP-Server}"
TARGET_ROOT="${REPO_ROOT}/third_party/nist-acvp-server"

if [[ ! -d "${SOURCE_ROOT}" ]]; then
  echo "NIST ACVP-Server checkout not found: ${SOURCE_ROOT}" >&2
  exit 1
fi

if [[ ! -d "${SOURCE_ROOT}/_config" || ! -d "${SOURCE_ROOT}/gen-val" ]]; then
  echo "Expected _config/ and gen-val/ under ${SOURCE_ROOT}" >&2
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
  ML-DSA-keyGen-FIPS204 \
  ML-DSA-sigGen-FIPS204 \
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
    echo "Warning: missing ML-DSA json-files directory: ${name}" >&2
  fi
done

if [[ -f "${SOURCE_ROOT}/README.md" ]]; then
  cp "${SOURCE_ROOT}/README.md" "${TARGET_ROOT}/NIST_README.md"
fi

source_commit="$(git -C "${SOURCE_ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown")"
copied_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "${TARGET_ROOT}/NIST_SOURCE.md" <<EOF
# NIST ACVP-Server Source

- copied from local path: ${SOURCE_ROOT}
- source git commit: ${source_commit}
- copied timestamp: ${copied_at}
- integration note: NIST code is copied into this repository; it is not a git submodule.

This directory vendors the NIST ACVP-Server Gen/Val code needed by the local
FIPS204 demo integration. Re-run scripts/nist/copy_nist_genval.sh to refresh it
from the local ACVP-Server checkout.
EOF

echo "Copied NIST Gen/Val code to ${TARGET_ROOT}"
