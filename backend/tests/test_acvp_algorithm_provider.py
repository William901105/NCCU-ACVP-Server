from __future__ import annotations

import pytest

from app.acvp_core.registry import AlgorithmProviderRegistry, DuplicateProviderError, ProviderNotFoundError, get_provider
from app.acvp_mldsa.provider import MldsaProvider, ensure_mldsa_provider_registered, get_mldsa_provider


def setup_module() -> None:
    ensure_mldsa_provider_registered()


def test_default_registry_has_mldsa_schema_provider_for_all_modes() -> None:
    for mode in ("keyGen", "sigGen", "sigVer"):
        assert get_provider("ML-DSA", mode, "FIPS204").supports("ML-DSA", mode, "FIPS204")


def test_unknown_algorithm_raises_clear_registry_error() -> None:
    registry = AlgorithmProviderRegistry()
    registry.register_provider(get_mldsa_provider())

    with pytest.raises(ProviderNotFoundError):
        registry.get_provider("unknown", "keyGen", "FIPS204")


def test_duplicate_provider_registration_is_rejected() -> None:
    registry = AlgorithmProviderRegistry()
    registry.register_provider(MldsaProvider())
    with pytest.raises(DuplicateProviderError):
        registry.register_provider(MldsaProvider())


def test_mldsa_provider_validates_and_negotiates_keygen_registration() -> None:
    provider = get_mldsa_provider()
    registration = provider.validate_registration(
        {
            "algorithm": "ML-DSA",
            "mode": "keyGen",
            "revision": "FIPS204",
            "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
            "parameterSets": ["ML-DSA-44"],
        }
    )
    negotiated = provider.negotiate_capabilities(registration)

    assert registration["algorithm"] == "ML-DSA"
    assert negotiated["negotiated"][0]["mode"] == "keyGen"
