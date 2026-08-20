#!/usr/bin/env bash
set -Eeuo pipefail

ORLEANS_DLL="/opt/acvp/nist/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll"
RUNNER_DLL="${ACVP_GENVAL_RUNNER_DLL:-/opt/acvp/nist/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll}"
ARTIFACT_ROOT="${ACVP_GENVAL_ARTIFACT_ROOT:-/var/lib/acvp/artifacts}"

require_identifier() {
    local name="$1"
    local value="$2"
    if [[ ! "${value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "${name} must be a PostgreSQL identifier containing letters, digits, or underscores." >&2
        exit 64
    fi
}

configure_database_url() {
    if [[ -n "${DATABASE_URL:-}" ]]; then
        export DATABASE_URL
        return
    fi

    local password_file="${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"
    local database_name="${POSTGRES_DB:-acvp}"
    local database_user="${POSTGRES_USER:-acvp_app}"
    local database_host="${POSTGRES_HOST:-postgres}"
    local database_port="${POSTGRES_PORT:-5432}"
    local encoded_password

    require_identifier "POSTGRES_DB" "${database_name}"
    require_identifier "POSTGRES_USER" "${database_user}"
    if [[ ! "${database_port}" =~ ^[0-9]+$ ]]; then
        echo "POSTGRES_PORT must be numeric." >&2
        exit 64
    fi
    if [[ ! -r "${password_file}" ]]; then
        echo "PostgreSQL password secret is not readable at ${password_file}." >&2
        exit 78
    fi

    encoded_password="$({ python -c 'import sys; from urllib.parse import quote; print(quote(sys.stdin.read().rstrip("\n"), safe=""))'; } < "${password_file}")"
    if [[ -z "${encoded_password}" ]]; then
        echo "PostgreSQL password secret must not be empty." >&2
        exit 78
    fi

    DATABASE_URL="postgresql://${database_user}:${encoded_password}@${database_host}:${database_port}/${database_name}"
    export DATABASE_URL
}

wait_for_orleans() {
    local attempt
    for attempt in $(seq 1 90); do
        if ! kill -0 "${orleans_pid}" 2>/dev/null; then
            echo "Orleans exited before its gateway became ready." >&2
            wait "${orleans_pid}" || true
            return 1
        fi
        if python /opt/acvp/bin/engine-healthcheck.py --orleans-only 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "Timed out waiting for the Orleans gateway on 127.0.0.1:30000." >&2
    return 1
}

shutdown() {
    trap - TERM INT EXIT
    if [[ -n "${api_pid:-}" ]] && kill -0 "${api_pid}" 2>/dev/null; then
        kill -TERM "${api_pid}" 2>/dev/null || true
    fi
    if [[ -n "${orleans_pid:-}" ]] && kill -0 "${orleans_pid}" 2>/dev/null; then
        kill -TERM "${orleans_pid}" 2>/dev/null || true
    fi
    [[ -z "${api_pid:-}" ]] || wait "${api_pid}" 2>/dev/null || true
    [[ -z "${orleans_pid:-}" ]] || wait "${orleans_pid}" 2>/dev/null || true
}

configure_database_url

if [[ ! -f "${RUNNER_DLL}" ]]; then
    echo "NIST GenVal Runner is missing at ${RUNNER_DLL}." >&2
    exit 78
fi
if [[ ! -f "${ORLEANS_DLL}" ]]; then
    echo "Orleans ServerHost is missing at ${ORLEANS_DLL}." >&2
    exit 78
fi

mkdir -p "${ARTIFACT_ROOT}" /tmp/dotnet
if [[ ! -w "${ARTIFACT_ROOT}" ]]; then
    echo "GenVal artifact root is not writable: ${ARTIFACT_ROOT}." >&2
    exit 73
fi

trap shutdown TERM INT EXIT

dotnet "${ORLEANS_DLL}" --console &
orleans_pid=$!
wait_for_orleans

uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 &
api_pid=$!

set +e
wait -n "${orleans_pid}" "${api_pid}"
status=$?
set -e

exit "${status}"
