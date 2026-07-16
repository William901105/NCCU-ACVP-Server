from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.genval import GenValExecutionError, GenValSettings
from app.genval.nist_cli_provider import NistCliGenValProvider
import app.genval.nist_cli_provider as nist_cli_provider


def test_validation_accepts_nonzero_exit_when_validation_json_exists(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    provider, work_dir, internal_projection, response = _provider_fixture(tmp_path)

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        output_dir = Path(kwargs["cwd"])
        (output_dir / "validation.json").write_text(
            json.dumps(
                {
                    "vsId": 1,
                    "disposition": "failed",
                    "tests": [{"tcId": 1, "result": "failed", "reason": "mismatch"}],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            13,
            stdout="Info GenValApp Running in Validate mode",
            stderr="",
        )

    monkeypatch.setattr(nist_cli_provider.shutil, "which", lambda _: "/usr/bin/dotnet")
    monkeypatch.setattr(nist_cli_provider.subprocess, "run", fake_run)

    validation_path = provider.validate(internal_projection, response, work_dir)

    assert validation_path == work_dir / "validation.json"
    assert json.loads(validation_path.read_text(encoding="utf-8"))["disposition"] == "failed"
    assert (work_dir / "validation.stdout.txt").read_text(encoding="utf-8")
    assert (work_dir / "validation.stderr.txt").exists()


def test_validation_nonzero_exit_without_validation_json_still_raises(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    provider, work_dir, internal_projection, response = _provider_fixture(tmp_path)
    stale_validation = work_dir / "validation.json"
    stale_validation.write_text('{"disposition":"passed"}', encoding="utf-8")

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            13,
            stdout="Info GenValApp Running in Validate mode",
            stderr="TestCaseValidatorError",
        )

    monkeypatch.setattr(nist_cli_provider.shutil, "which", lambda _: "/usr/bin/dotnet")
    monkeypatch.setattr(nist_cli_provider.subprocess, "run", fake_run)

    with pytest.raises(GenValExecutionError, match="exit code 13"):
        provider.validate(internal_projection, response, work_dir)
    assert not stale_validation.exists()


def test_timeout_with_byte_output_is_recorded_and_mapped(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    provider, work_dir, internal_projection, response = _provider_fixture(tmp_path)

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            command,
            timeout=5,
            output=b"partial stdout\n",
            stderr=b"partial stderr\n",
        )

    monkeypatch.setattr(nist_cli_provider.shutil, "which", lambda _: "/usr/bin/dotnet")
    monkeypatch.setattr(nist_cli_provider.subprocess, "run", fake_run)

    with pytest.raises(GenValExecutionError, match="timed out after 5 seconds"):
        provider.validate(internal_projection, response, work_dir)
    assert (work_dir / "validation.stdout.txt").read_text(encoding="utf-8") == "partial stdout\n"
    assert (work_dir / "validation.stderr.txt").read_text(encoding="utf-8") == "partial stderr\n"


def _provider_fixture(
    tmp_path: Path,
) -> tuple[NistCliGenValProvider, Path, Path, Path]:
    runner = tmp_path / "runner.dll"
    runner.write_text("", encoding="utf-8")
    settings = GenValSettings(
        project_root=tmp_path,
        runner_dll=runner,
        artifact_root=tmp_path / "artifacts",
        timeout_seconds=5,
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    internal_projection = tmp_path / "internalProjection.json"
    response = tmp_path / "response.json"
    internal_projection.write_text("{}", encoding="utf-8")
    response.write_text("{}", encoding="utf-8")
    return NistCliGenValProvider(settings), work_dir, internal_projection, response
