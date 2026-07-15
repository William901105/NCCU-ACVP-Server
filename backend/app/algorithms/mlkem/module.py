from __future__ import annotations

from typing import Any, Dict, Optional

from ...acvp_core.algorithm_descriptor import AlgorithmDescriptor
from ...acvp_core.algorithm_identity import AlgorithmIdentity
from .capabilities import negotiate_mlkem_capabilities
from .descriptor import build_mlkem_descriptor
from .nist_mapper import map_mlkem_registration_to_nist
from .validation_normalizer import normalize_nist_validation
from .validators import (
    validate_mlkem_registration,
    validate_mlkem_response,
    validate_mlkem_vector_set,
)


class MlkemAlgorithmModule:
    provider_id = "nist-ml-kem-fips203"

    def __init__(self) -> None:
        self.descriptor: AlgorithmDescriptor = build_mlkem_descriptor()

    def supports(self, identity: AlgorithmIdentity) -> bool:
        return identity in self.descriptor.identities()

    def validate_registration(self, registration: Dict[str, Any]) -> Dict[str, Any]:
        return validate_mlkem_registration(registration)

    def negotiate_capabilities(self, registration: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self.validate_registration(registration)
        return negotiate_mlkem_capabilities({"algorithms": [normalized]})

    def validate_prompt(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        return validate_mlkem_vector_set(prompt)

    def validate_response(
        self,
        response: Dict[str, Any],
        *,
        expected_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        return validate_mlkem_response(response, expected_mode=expected_mode)

    def to_nist_registration(
        self,
        registration: Dict[str, Any],
        *,
        vs_id: int,
        is_sample: bool,
    ) -> Dict[str, Any]:
        return map_mlkem_registration_to_nist(
            registration,
            vs_id=vs_id,
            is_sample=is_sample,
        )

    def normalize_nist_validation(
        self,
        validation: Dict[str, Any],
        *,
        prompt: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return normalize_nist_validation(validation, prompt=prompt)
