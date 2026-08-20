#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import psycopg


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def get_database_url() -> str:
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return configured

    password_file = Path(
        os.environ.get("POSTGRES_PASSWORD_FILE", "/run/secrets/postgres_password")
    )
    try:
        password = password_file.read_text(encoding="utf-8").rstrip("\n")
    except OSError as exc:
        fail(f"PostgreSQL password secret is unavailable: {exc}")
    if not password:
        fail("PostgreSQL password secret is empty.")

    user = os.environ.get("POSTGRES_USER", "acvp_app")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "acvp")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )


def tcp_port_is_listening(port: int) -> bool:
    expected_port = f"{port:04X}"
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            rows = table.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) < 4:
                continue
            local_address = fields[1]
            state = fields[3]
            if state == "0A" and local_address.rsplit(":", 1)[-1] == expected_port:
                return True
    return False


def check_orleans() -> None:
    if not tcp_port_is_listening(30000):
        fail("Orleans gateway is not listening on port 30000.")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--orleans-only":
        check_orleans()
        return
    if len(sys.argv) != 1:
        fail("Usage: engine-healthcheck.py [--orleans-only]")

    runner = Path(
        os.environ.get(
            "ACVP_GENVAL_RUNNER_DLL",
            "/opt/acvp/nist/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll",
        )
    )
    artifact_root = Path(
        os.environ.get("ACVP_GENVAL_ARTIFACT_ROOT", "/var/lib/acvp/artifacts")
    )
    database_url = get_database_url()

    if not runner.is_file():
        fail(f"Runner DLL is missing: {runner}")
    if not artifact_root.is_dir() or not os.access(artifact_root, os.W_OK):
        fail(f"Artifact root is unavailable: {artifact_root}")

    check_orleans()

    try:
        with urlopen("http://127.0.0.1:8000/api/health", timeout=3) as response:
            payload = json.load(response)
        if payload != {"status": "ok"}:
            fail(f"Unexpected FastAPI health response: {payload!r}")
    except Exception as exc:
        fail(f"FastAPI health endpoint is unavailable: {exc}")

    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            row = connection.execute("SELECT 1").fetchone()
        if row != (1,):
            fail(f"Unexpected PostgreSQL health result: {row!r}")
    except Exception as exc:
        fail(f"PostgreSQL is unavailable: {exc}")


if __name__ == "__main__":
    main()
