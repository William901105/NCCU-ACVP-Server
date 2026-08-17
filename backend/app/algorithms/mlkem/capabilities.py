from __future__ import annotations

from typing import Any, Dict, List

from ...acvp_core.schema_error import AcvpSchemaError
from .common import child_path, require_array, require_field, require_object
from .constants import ALGORITHM, REVISION
from .registration_schema import validate_registration


NEXT_VECTOR_GENERATION_ACTION = (
    "NIST GenVal vector generation is available for negotiated capabilities."
)


def negotiate_mlkem_capabilities(
    container: Dict[str, Any],
) -> Dict[str, Any]:
    obj = require_object(container, "$")
    registrations = require_array(
        require_field(obj, "algorithms", "$"),
        "$.algorithms",
    )
    negotiated: List[Dict[str, Any]] = []

    for index, item in enumerate(registrations):
        path = child_path("$.algorithms", index)
        try:
            registration = validate_registration(item)
        except AcvpSchemaError as exc:
            error_path = exc.path or "$"
            suffix = error_path[1:] if error_path.startswith("$") else error_path
            raise AcvpSchemaError(exc.code, exc.message, f"{path}{suffix}") from exc
        entry: Dict[str, Any] = {
            "mode": registration["mode"],
            "parameterSets": list(registration["parameterSets"]),
        }
        if registration["mode"] == "encapDecap":
            entry["functions"] = list(registration["functions"])
        entry["status"] = "accepted"
        negotiated.append(entry)

    if not negotiated:
        raise AcvpSchemaError(
            "UNSUPPORTED_CAPABILITIES",
            "No supported ML-KEM capabilities were negotiated.",
            "$.algorithms",
        )
    return {
        "algorithm": ALGORITHM,
        "revision": REVISION,
        "negotiated": negotiated,
        "unsupported": [],
        "warnings": [],
        "nextAction": NEXT_VECTOR_GENERATION_ACTION,
    }
