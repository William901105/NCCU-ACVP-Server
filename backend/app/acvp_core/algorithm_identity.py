from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmIdentity:
    algorithm: str
    mode: str
    revision: str

    def __post_init__(self) -> None:
        for field_name in ("algorithm", "mode", "revision"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def __str__(self) -> str:
        return f"{self.algorithm}/{self.mode}/{self.revision}"
