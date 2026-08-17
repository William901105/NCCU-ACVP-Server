from __future__ import annotations

from ..algorithms.mldsa import MldsaAlgorithmModule, MldsaTr1AlgorithmModule
from ..algorithms.mlkem import MlkemAlgorithmModule
from .registry import AlgorithmModuleRegistry


def build_algorithm_registry() -> AlgorithmModuleRegistry:
    registry = AlgorithmModuleRegistry()
    registry.register_module(MldsaAlgorithmModule())
    registry.register_module(MldsaTr1AlgorithmModule())
    registry.register_module(MlkemAlgorithmModule())
    return registry
