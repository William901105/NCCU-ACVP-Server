from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

from .artifacts import GenValArtifacts


class GenValProvider(ABC):
    @abstractmethod
    def check_registration(self, registration: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, registration: Dict[str, Any], work_dir: Path) -> GenValArtifacts:
        raise NotImplementedError

    @abstractmethod
    def validate(self, internal_projection: Path, response: Path, work_dir: Path) -> Path:
        raise NotImplementedError
