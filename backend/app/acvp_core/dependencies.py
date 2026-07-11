from __future__ import annotations

from fastapi import Request

from .registry import AlgorithmModuleRegistry


def get_algorithm_registry(request: Request) -> AlgorithmModuleRegistry:
    registry = getattr(request.app.state, "algorithm_registry", None)
    if not isinstance(registry, AlgorithmModuleRegistry):
        raise RuntimeError("Algorithm module registry is not initialized.")
    return registry
