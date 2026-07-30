from __future__ import annotations

from typing import Any, Dict

from ...acvp_core.schema_error import AcvpSchemaError
from .common import (
    child_path,
    require_absent,
    require_allowed_fields,
    require_enum,
    require_enum_array,
    require_field,
    require_object,
    require_string,
    validate_prereq_vals,
)
from .constants import (
    ALGORITHM,
    FUNCTIONS,
    KEY_FORMATS,
    MODES,
    PARAMETER_SETS,
    PREREQUISITE_ALGORITHMS,
    REVISION,
    REVISION_TR1,
)
from .normalize import normalize_acvp_container


_COMMON_FIELDS = {"algorithm", "mode", "revision", "parameterSets", "prereqVals"}


def validate_registration(payload: Any, *, revision: str = REVISION) -> Dict[str, Any]:
    obj = require_object(normalize_acvp_container(payload), "$")
    if obj.get("acvVersion") is None:
        obj.pop("acvVersion", None)
    supports_key_formats = revision == REVISION_TR1
    allowed = set(_COMMON_FIELDS)
    if obj.get("mode") == "encapDecap":
        allowed.add("functions")
        if supports_key_formats:
            allowed.add("keyFormats")
    require_allowed_fields(obj, allowed, "$")

    algorithm = require_string(require_field(obj, "algorithm", "$"), "$.algorithm")
    if algorithm != ALGORITHM:
        raise AcvpSchemaError(
            "unsupported_algorithm",
            f"Unsupported algorithm: {algorithm}",
            "$.algorithm",
        )
    registration_revision = require_string(
        require_field(obj, "revision", "$"), "$.revision"
    )
    if registration_revision != revision:
        raise AcvpSchemaError(
            "unsupported_revision",
            f"Unsupported revision: {registration_revision}",
            "$.revision",
        )
    mode = require_enum(
        require_field(obj, "mode", "$"),
        MODES,
        "$.mode",
        code="invalid_mode",
    )
    obj["parameterSets"] = require_enum_array(
        require_field(obj, "parameterSets", "$"),
        PARAMETER_SETS,
        "$.parameterSets",
        code="invalid_parameter_set",
    )
    validate_prereq_vals(
        obj,
        "$",
        allowed_algorithms=PREREQUISITE_ALGORITHMS,
    )

    if mode == "keyGen":
        require_absent(obj, "functions", "$", "mode is keyGen")
        require_absent(obj, "keyFormats", "$", "mode is keyGen")
    else:
        obj["functions"] = require_enum_array(
            require_field(obj, "functions", "$"),
            FUNCTIONS,
            "$.functions",
            code="invalid_function",
        )
        if supports_key_formats:
            obj["keyFormats"] = require_enum_array(
                require_field(obj, "keyFormats", "$"),
                KEY_FORMATS,
                "$.keyFormats",
                code="invalid_key_format",
            )
        else:
            require_absent(obj, "keyFormats", "$", "revision is FIPS203")
    return obj
