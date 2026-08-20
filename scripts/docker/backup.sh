#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    echo "Usage: $0 BACKUP_DIRECTORY" >&2
}

if [[ $# -ne 1 ]]; then
    usage
    exit 64
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_PARENT="$(realpath -m "$1")"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_PARENT}/nccu-acvp-${TIMESTAMP}"
SERVICES_STOPPED=0

if [[ "${BACKUP_PARENT}" == "/" ]]; then
    echo "Refusing to use the filesystem root as the backup directory." >&2
    exit 64
fi
if [[ -e "${BACKUP_DIR}" ]]; then
    echo "Backup target already exists: ${BACKUP_DIR}" >&2
    exit 73
fi

restart_services() {
    if [[ "${SERVICES_STOPPED}" -eq 1 ]]; then
        docker compose start acvp-engine frontend >/dev/null 2>&1 || true
    fi
}
trap restart_services EXIT

mkdir -p "${BACKUP_DIR}"
cd "${REPO_ROOT}"

docker compose stop frontend acvp-engine
SERVICES_STOPPED=1

docker compose exec -T postgres sh -ec \
    'exec pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format custom' \
    > "${BACKUP_DIR}/postgres.dump"

docker compose run --rm --no-deps --entrypoint /bin/tar acvp-engine \
    -C /var/lib/acvp/artifacts -czf - . > "${BACKUP_DIR}/genval-artifacts.tar.gz"

git -C "${REPO_ROOT}" rev-parse HEAD > "${BACKUP_DIR}/git-commit.txt"
docker compose images > "${BACKUP_DIR}/images.txt"
sha256sum \
    "${BACKUP_DIR}/postgres.dump" \
    "${BACKUP_DIR}/genval-artifacts.tar.gz" \
    > "${BACKUP_DIR}/SHA256SUMS"

docker compose up --detach --wait acvp-engine frontend
SERVICES_STOPPED=0

echo "Backup completed: ${BACKUP_DIR}"
