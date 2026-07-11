from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from .algorithm_descriptor import AlgorithmDescriptor
from .algorithm_identity import AlgorithmIdentity


@runtime_checkable
class AcvpAlgorithmModule(Protocol):
    provider_id: str
    descriptor: AlgorithmDescriptor

    def supports(self, identity: AlgorithmIdentity) -> bool:
        ...

    def validate_registration(self, registration: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def negotiate_capabilities(self, registration: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def validate_prompt(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def validate_response(
        self,
        response: Dict[str, Any],
        *,
        expected_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    def to_nist_registration(
        self,
        registration: Dict[str, Any],
        *,
        vs_id: int,
        is_sample: bool,
    ) -> Dict[str, Any]:
        ...

    def normalize_nist_validation(
        self,
        validation: Dict[str, Any],
        *,
        prompt: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...


def normalize_module_validation(
    module: AcvpAlgorithmModule,
    validation: Dict[str, Any],
    *,
    prompt: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return module.normalize_nist_validation(validation, prompt=prompt)
