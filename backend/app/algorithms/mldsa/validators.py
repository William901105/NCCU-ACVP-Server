from __future__ import annotations

from typing import Any, Dict, Optional

from .registration_schema import validate_registration
from .response_schema import validate_response
from .vector_schema import validate_vector_set


def validate_mldsa_registration(payload: Any) -> Dict[str, Any]:
    return validate_registration(payload)


def validate_mldsa_vector_set(payload: Any) -> Dict[str, Any]:
    return validate_vector_set(payload)


def validate_mldsa_response(payload: Any, expected_mode: Optional[str] = None) -> Dict[str, Any]:
    return validate_response(payload, expected_mode=expected_mode)
