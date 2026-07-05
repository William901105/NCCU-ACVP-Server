from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GenValArtifacts:
    registration: Path
    prompt: Path
    internal_projection: Path
    expected_results: Optional[Path]
    stdout: Optional[Path]
    stderr: Optional[Path]


def session_artifact_dir(root: Path, session_id: str) -> Path:
    return root / session_id


def vector_set_artifact_dir(root: Path, session_id: str, vector_set_id: str) -> Path:
    return session_artifact_dir(root, session_id) / "vectorSets" / vector_set_id
