from __future__ import annotations

from typing import Any, Dict, Optional

from .common import require_object
from ...acvp_core.schema_error import AcvpSchemaError


def normalize_acvp_container(payload: Any) -> Dict[str, Any]:
    """
    Accept either the NIST ACVP array container or the legacy object container.
    Return one normalized dict containing acvVersion plus vector-set/response body.

    Aligned with NIST ACVP ML-DSA draft-celi-acvp-ml-dsa-01.
    """
    if isinstance(payload, list):
        return _normalize_array_container(payload)

    if isinstance(payload, dict):
        normalized = dict(payload)
        normalized.setdefault("acvVersion", None)
        return normalized

    raise AcvpSchemaError("invalid_container", "ACVP payload must be an object or array", "$")


def _normalize_array_container(payload: Any) -> Dict[str, Any]:
    if len(payload) < 2:
        raise AcvpSchemaError(
            "invalid_container",
            "ACVP array container must include version object and body object",
            "$",
        )

    version_obj = require_object(payload[0], "$[0]")
    acv_version = version_obj.get("acvVersion")
    if acv_version is not None and not isinstance(acv_version, str):
        raise AcvpSchemaError("invalid_type", "acvVersion must be a string", "$[0].acvVersion")

    body_index: Optional[int] = None
    for index, item in enumerate(payload[1:], start=1):
        if isinstance(item, dict):
            body_index = index
            break

    if body_index is None:
        raise AcvpSchemaError("invalid_container", "ACVP array container missing body object", "$")

    body = dict(require_object(payload[body_index], f"$[{body_index}]"))
    body["acvVersion"] = acv_version
    return body
