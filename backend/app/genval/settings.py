from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GenValSettings:
    project_root: Path
    runner_dll: Path
    artifact_root: Path
    timeout_seconds: int


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_genval_settings() -> GenValSettings:
    project_root = get_project_root()
    runner_dll = Path(
        os.environ.get(
            "ACVP_GENVAL_RUNNER_DLL",
            project_root / ".nist-bin" / "genval-runner" / "NIST.CVP.ACVTS.Generation.GenValApp.dll",
        )
    ).expanduser()
    artifact_root = Path(
        os.environ.get(
            "ACVP_GENVAL_ARTIFACT_ROOT",
            project_root / "backend" / "data" / "acvp-sessions",
        )
    ).expanduser()
    timeout_seconds = int(os.environ.get("ACVP_GENVAL_TIMEOUT_SECONDS", "120"))
    return GenValSettings(
        project_root=project_root,
        runner_dll=runner_dll,
        artifact_root=artifact_root,
        timeout_seconds=timeout_seconds,
    )
