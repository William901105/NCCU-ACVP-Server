from __future__ import annotations

from typing import Dict, List, Optional

from ..acvp_core.registry import (
    DEFAULT_REGISTRY,
    AlgorithmProviderRegistry,
    DuplicateProviderError,
    ProviderNotFoundError,
)
from ..acvp_protocol.capabilities import negotiate_mldsa_capabilities
from .constants import ALGORITHM, REVISION
from .validators import (
    validate_mldsa_registration,
    validate_mldsa_response,
    validate_mldsa_vector_set,
)


class MldsaProvider:
    """Registration and schema provider; NIST GenVal owns execution."""

    algorithm = ALGORITHM
    revisions = [REVISION]
    modes = ["keyGen", "sigGen", "sigVer"]

    def supports(self, algorithm: str, mode: str, revision: str) -> bool:
        return algorithm == self.algorithm and revision in self.revisions and mode in self.modes

    def validate_registration(self, registration: Dict[str, object]) -> Dict[str, object]:
        return validate_mldsa_registration(registration)

    def negotiate_capabilities(self, registration: Dict[str, object]) -> Dict[str, object]:
        normalized = self.validate_registration(registration)
        return negotiate_mldsa_capabilities({"algorithms": [normalized]})

    def validate_prompt(self, prompt: Dict[str, object]) -> Dict[str, object]:
        return validate_mldsa_vector_set(prompt)

    def validate_response(
        self,
        response: Dict[str, object],
        *,
        expected_mode: Optional[str] = None,
    ) -> Dict[str, object]:
        return validate_mldsa_response(response, expected_mode=expected_mode)


_MLDSA_PROVIDER = MldsaProvider()


def get_mldsa_provider() -> MldsaProvider:
    return _MLDSA_PROVIDER


def register_mldsa_provider(registry: Optional[AlgorithmProviderRegistry] = None) -> MldsaProvider:
    target = registry or DEFAULT_REGISTRY
    target.register_provider(_MLDSA_PROVIDER)
    return _MLDSA_PROVIDER


def ensure_mldsa_provider_registered(registry: Optional[AlgorithmProviderRegistry] = None) -> MldsaProvider:
    target = registry or DEFAULT_REGISTRY
    missing_modes: List[str] = []
    existing_providers = []
    for mode in _MLDSA_PROVIDER.modes:
        try:
            existing_providers.append(target.get_provider(ALGORITHM, mode, REVISION))
        except ProviderNotFoundError:
            missing_modes.append(mode)
    if not missing_modes:
        return _MLDSA_PROVIDER
    if existing_providers:
        raise DuplicateProviderError(ALGORITHM, missing_modes[0], REVISION)
    return register_mldsa_provider(target)
