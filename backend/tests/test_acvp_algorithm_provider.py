from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.acvp_core.algorithm_descriptor import AlgorithmDescriptor
from app.acvp_core.algorithm_identity import AlgorithmIdentity
from app.acvp_core.bootstrap import build_algorithm_registry
from app.acvp_core.registry import (
    AlgorithmModuleRegistry,
    DuplicateModuleError,
    ModuleNotFoundError,
)
from app.algorithms.mldsa import MldsaAlgorithmModule
from app.algorithms.mlkem import MlkemAlgorithmModule


def test_algorithm_identity_validates_hashes_and_formats() -> None:
    identity = AlgorithmIdentity("ML-DSA", "keyGen", "FIPS204")

    assert identity == AlgorithmIdentity("ML-DSA", "keyGen", "FIPS204")
    assert len({identity, AlgorithmIdentity("ML-DSA", "keyGen", "FIPS204")}) == 1
    assert str(identity) == "ML-DSA/keyGen/FIPS204"
    for values in (("", "keyGen", "FIPS204"), ("ML-DSA", "", "FIPS204"), ("ML-DSA", "keyGen", "")):
        with pytest.raises(ValueError):
            AlgorithmIdentity(*values)


def test_descriptor_is_immutable_and_serialization_is_detached() -> None:
    descriptor = _descriptor("provider-one", "ALG", ("modeB", "modeA"))
    first = descriptor.to_dict()
    first["modes"].append("changed")
    first["metadata"]["values"].append(3)

    assert descriptor.to_dict()["modes"] == ["modeB", "modeA"]
    assert descriptor.to_dict()["metadata"] == {"values": [1, 2]}
    with pytest.raises(FrozenInstanceError):
        descriptor.algorithm = "changed"  # type: ignore[misc]


def test_registry_registers_gets_and_orders_modules_deterministically() -> None:
    registry = AlgorithmModuleRegistry()
    second = _StubModule(_descriptor("provider-z", "Z-ALG", ("mode",)))
    first = _StubModule(_descriptor("provider-a", "A-ALG", ("mode",)))
    registry.register_module(second)
    registry.register_module(first)

    identity = AlgorithmIdentity("A-ALG", "mode", "R1")
    assert registry.get_module(identity) is first
    assert registry.identities() == (
        AlgorithmIdentity("A-ALG", "mode", "R1"),
        AlgorithmIdentity("Z-ALG", "mode", "R1"),
    )
    assert [item["providerId"] for item in registry.list_descriptors()] == ["provider-a", "provider-z"]


def test_registry_rejects_duplicate_identity_and_provider_id() -> None:
    registry = AlgorithmModuleRegistry()
    registry.register_module(_StubModule(_descriptor("provider-one", "ALG", ("mode",))))

    with pytest.raises(DuplicateModuleError) as provider_error:
        registry.register_module(_StubModule(_descriptor("provider-one", "OTHER", ("mode",))))
    assert provider_error.value.provider_id == "provider-one"

    with pytest.raises(DuplicateModuleError) as identity_error:
        registry.register_module(_StubModule(_descriptor("provider-two", "ALG", ("mode",))))
    assert identity_error.value.identity == AlgorithmIdentity("ALG", "mode", "R1")


def test_unknown_identity_raises_module_not_found() -> None:
    with pytest.raises(ModuleNotFoundError):
        AlgorithmModuleRegistry().get_module(AlgorithmIdentity("UNKNOWN", "mode", "R1"))


def test_production_registry_contains_mldsa_and_mlkem_descriptors() -> None:
    registry = build_algorithm_registry()
    descriptors = registry.list_descriptors()
    descriptor = descriptors[0]

    assert len(registry) == 3
    assert descriptor["providerId"] == "nist-ml-dsa-fips204"
    assert descriptor["algorithm"] == "ML-DSA"
    assert descriptor["revision"] == "FIPS204"
    assert descriptor["modes"] == ["keyGen", "sigGen", "sigVer"]
    assert descriptor["parameterSets"] == ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]
    assert descriptor["workflowPolicy"] == "strict"
    assert descriptor["executionBackend"] == "nist-genval"
    for mode in descriptor["modes"]:
        assert isinstance(
            registry.get_module(AlgorithmIdentity("ML-DSA", mode, "FIPS204")),
            MldsaAlgorithmModule,
        )
    mlkem = descriptors[1]
    assert mlkem["providerId"] == "nist-ml-kem-fips203"
    for mode in mlkem["modes"]:
        assert isinstance(
            registry.get_module(AlgorithmIdentity("ML-KEM", mode, "FIPS203")),
            MlkemAlgorithmModule,
        )


def test_mldsa_module_validates_and_negotiates_keygen_registration() -> None:
    module = MldsaAlgorithmModule()
    registration = module.validate_registration(
        {
            "algorithm": "ML-DSA",
            "mode": "keyGen",
            "revision": "FIPS204",
            "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
            "parameterSets": ["ML-DSA-44"],
        }
    )
    negotiated = module.negotiate_capabilities(registration)

    assert registration["algorithm"] == "ML-DSA"
    assert negotiated["negotiated"][0]["mode"] == "keyGen"
    assert "local" not in str(negotiated).lower()


def _descriptor(provider_id: str, algorithm: str, modes: tuple) -> AlgorithmDescriptor:
    return AlgorithmDescriptor(
        provider_id=provider_id,
        algorithm=algorithm,
        revision="R1",
        display_name=algorithm,
        enabled=True,
        modes=modes,
        parameter_sets=("P1",),
        registration_schema_version="1",
        response_schema_version="1",
        execution_backend="nist-genval",
        nist_references=("https://example.test/spec",),
        capability_metadata={"metadata": {"values": [1, 2]}},
    )


class _StubModule:
    def __init__(self, descriptor: AlgorithmDescriptor) -> None:
        self.descriptor = descriptor
        self.provider_id = descriptor.provider_id

    def supports(self, identity: AlgorithmIdentity) -> bool:
        return identity in self.descriptor.identities()
