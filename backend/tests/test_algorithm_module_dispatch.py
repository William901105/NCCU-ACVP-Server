from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from app.acvp_core.algorithm_descriptor import AlgorithmDescriptor
from app.acvp_core.algorithm_identity import AlgorithmIdentity
from app.acvp_core.dependencies import get_algorithm_registry
from app.acvp_core.registry import AlgorithmModuleRegistry
from app.acvp_protocol import service
from app.acvp_protocol.routes import get_acvp_v1_algorithms
from app.main import app


class DummyAlgorithmModule:
    provider_id = "test-algorithm-module"
    descriptor = AlgorithmDescriptor(
        provider_id=provider_id,
        algorithm="TEST-ALGORITHM",
        revision="TEST1",
        display_name="Test Algorithm",
        enabled=True,
        modes=("testMode",),
        parameter_sets=("TEST-PARAM",),
        registration_schema_version="test-registration-1",
        response_schema_version="test-response-1",
        execution_backend="nist-genval",
        nist_references=("https://example.test/acvp",),
        capability_metadata={"testCapability": ["enabled"]},
    )

    def supports(self, identity: AlgorithmIdentity) -> bool:
        return identity in self.descriptor.identities()

    def validate_registration(self, registration: Dict[str, Any]) -> Dict[str, Any]:
        return {**registration, "validatedBy": self.provider_id}

    def negotiate_capabilities(self, registration: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "negotiated": [{"mode": registration["mode"], "status": "accepted"}],
            "unsupported": [],
            "warnings": [],
        }

    def validate_prompt(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        return prompt

    def validate_response(
        self,
        response: Dict[str, Any],
        *,
        expected_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        return response

    def to_nist_registration(
        self,
        registration: Dict[str, Any],
        *,
        vs_id: int,
        is_sample: bool,
    ) -> Dict[str, Any]:
        return {
            "vsId": vs_id,
            "algorithm": registration["algorithm"],
            "mode": registration["mode"],
            "revision": registration["revision"],
            "isSample": is_sample,
            "mappedBy": self.provider_id,
        }

    def normalize_nist_validation(
        self,
        validation: Dict[str, Any],
        *,
        prompt: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {"validation": validation, "normalizedBy": self.provider_id, "prompt": prompt}


def test_dummy_module_dispatches_without_production_changes() -> None:
    registry = _dummy_registry()
    identity = AlgorithmIdentity("TEST-ALGORITHM", "testMode", "TEST1")
    assert isinstance(registry.get_module(identity), DummyAlgorithmModule)

    container = service._validate_registration_container_with_modules(
        {"algorithms": [_registration()]},
        registry,
    )
    assert container["algorithms"][0]["validatedBy"] == "test-algorithm-module"

    mapped = service._map_registrations_to_nist(container, registry, is_sample=False)
    assert mapped == [
        {
            "vsId": 1,
            "algorithm": "TEST-ALGORITHM",
            "mode": "testMode",
            "revision": "TEST1",
            "isSample": False,
            "mappedBy": "test-algorithm-module",
        }
    ]

    normalized = service._normalize_validation_for_prompt(
        {"disposition": "passed"},
        {**_registration(), "testGroups": []},
        registry,
    )
    assert normalized["normalizedBy"] == "test-algorithm-module"


def test_algorithms_endpoint_uses_dependency_override_registry() -> None:
    registry = _dummy_registry()
    app.dependency_overrides[get_algorithm_registry] = lambda: registry
    try:
        dependency_registry = app.dependency_overrides[get_algorithm_registry]()
        response = get_acvp_v1_algorithms(dependency_registry)
    finally:
        app.dependency_overrides.pop(get_algorithm_registry, None)

    payload = response[1]
    assert payload["algorithms"] == registry.list_descriptors()
    assert payload["algorithms"][0]["providerId"] == "test-algorithm-module"


def test_application_lifespan_builds_production_registry_once() -> None:
    registry = asyncio.run(_registry_from_lifespan())

    assert len(registry) == 3
    assert [item["providerId"] for item in registry.list_descriptors()] == [
        "nist-ml-dsa-fips204",
        "nist-ml-kem-fips203",
        "nist-ml-kem-fips203-tr1",
    ]


def _dummy_registry() -> AlgorithmModuleRegistry:
    registry = AlgorithmModuleRegistry()
    registry.register_module(DummyAlgorithmModule())
    return registry


def _registration() -> Dict[str, Any]:
    return {
        "algorithm": "TEST-ALGORITHM",
        "mode": "testMode",
        "revision": "TEST1",
    }


async def _registry_from_lifespan() -> AlgorithmModuleRegistry:
    async with app.router.lifespan_context(app):
        return app.state.algorithm_registry
