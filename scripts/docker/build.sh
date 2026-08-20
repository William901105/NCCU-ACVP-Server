#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required." >&2
    exit 127
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required." >&2
    exit 127
fi

ACVP_VCS_REF="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
ACVP_BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export ACVP_VCS_REF ACVP_BUILD_DATE

if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
    echo "WARNING: the working tree is dirty; the images include uncommitted content." >&2
fi

cd "${REPO_ROOT}"
exec docker compose build "$@"
