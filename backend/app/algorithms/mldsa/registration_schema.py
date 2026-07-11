from __future__ import annotations

from typing import Any, Dict, List

from .common import (
    child_path,
    require_bool_array,
    require_enum,
    require_enum_array,
    require_field,
    require_object,
    require_string,
    validate_domain_list,
    validate_prereq_vals,
)
from .constants import (
    ALGORITHM,
    DOMAIN_CONSTRAINTS,
    HASH_ALGORITHMS,
    MODES,
    PARAMETER_SETS,
    PRE_HASH_VALUES,
    REVISION,
    SIGNATURE_INTERFACES,
)
from ...acvp_core.schema_error import AcvpSchemaError
from .normalize import normalize_acvp_container


def validate_registration(payload: Any) -> Dict[str, Any]:
    obj = require_object(normalize_acvp_container(payload), "$")
    _validate_common_registration(obj, "$")
    mode = require_enum(require_field(obj, "mode", "$"), MODES, "$.mode", code="invalid_mode")

    if mode == "keyGen":
        validate_keygen_registration(obj, "$")
    elif mode == "sigGen":
        validate_siggen_registration(obj, "$")
    elif mode == "sigVer":
        validate_sigver_registration(obj, "$")
    else:
        raise AcvpSchemaError("invalid_mode", f"Unsupported mode: {mode}", "$.mode")

    return obj


def validate_keygen_registration(obj: Dict[str, Any], path: str = "$") -> Dict[str, Any]:
    require_enum_array(
        require_field(obj, "parameterSets", path),
        PARAMETER_SETS,
        child_path(path, "parameterSets"),
        code="invalid_parameter_set",
    )
    return obj


def validate_siggen_registration(obj: Dict[str, Any], path: str = "$") -> Dict[str, Any]:
    require_bool_array(require_field(obj, "deterministic", path), child_path(path, "deterministic"))
    _validate_signature_interface_registration(obj, path)
    _validate_capabilities(obj, path, require_hash_alg=_uses_pre_hash(obj))
    return obj


def validate_sigver_registration(obj: Dict[str, Any], path: str = "$") -> Dict[str, Any]:
    _validate_signature_interface_registration(obj, path)
    _validate_capabilities(obj, path, require_hash_alg=_uses_pre_hash(obj))
    return obj


def _validate_common_registration(obj: Dict[str, Any], path: str) -> None:
    algorithm = require_string(require_field(obj, "algorithm", path), child_path(path, "algorithm"))
    if algorithm != ALGORITHM:
        raise AcvpSchemaError("unsupported_algorithm", f"Unsupported algorithm: {algorithm}", child_path(path, "algorithm"))

    revision = require_string(require_field(obj, "revision", path), child_path(path, "revision"))
    if revision != REVISION:
        raise AcvpSchemaError("unsupported_revision", f"Unsupported revision: {revision}", child_path(path, "revision"))

    validate_prereq_vals(obj, path)


def _validate_signature_interface_registration(obj: Dict[str, Any], path: str) -> None:
    signature_interfaces = set(
        require_enum_array(
            require_field(obj, "signatureInterfaces", path),
            SIGNATURE_INTERFACES,
            child_path(path, "signatureInterfaces"),
        )
    )

    if "external" in signature_interfaces:
        require_enum_array(
            require_field(obj, "preHash", path),
            PRE_HASH_VALUES,
            child_path(path, "preHash"),
        )
    elif "preHash" in obj:
        raise AcvpSchemaError(
            "invalid_conditional_field",
            "preHash is only valid when signatureInterfaces includes external",
            child_path(path, "preHash"),
        )

    if "internal" in signature_interfaces:
        require_bool_array(require_field(obj, "externalMu", path), child_path(path, "externalMu"))
    elif "externalMu" in obj:
        raise AcvpSchemaError(
            "invalid_conditional_field",
            "externalMu is only valid when signatureInterfaces includes internal",
            child_path(path, "externalMu"),
        )


def _validate_capabilities(
    obj: Dict[str, Any],
    path: str,
    require_hash_alg: bool,
) -> List[Dict[str, Any]]:
    capabilities = require_field(obj, "capabilities", path)
    capability_array = require_enum_capability_array(capabilities, child_path(path, "capabilities"))

    for index, capability in enumerate(capability_array):
        capability_path = child_path(child_path(path, "capabilities"), index)
        require_enum_array(
            require_field(capability, "parameterSets", capability_path),
            PARAMETER_SETS,
            child_path(capability_path, "parameterSets"),
            code="invalid_parameter_set",
        )
        validate_domain_list(
            require_field(capability, "messageLength", capability_path),
            child_path(capability_path, "messageLength"),
            DOMAIN_CONSTRAINTS["messageLength"],
        )
        validate_domain_list(
            require_field(capability, "contextLength", capability_path),
            child_path(capability_path, "contextLength"),
            DOMAIN_CONSTRAINTS["contextLength"],
        )
        if require_hash_alg or "hashAlgs" in capability:
            require_enum_array(
                require_field(capability, "hashAlgs", capability_path),
                HASH_ALGORITHMS,
                child_path(capability_path, "hashAlgs"),
            )

    return capability_array


def require_enum_capability_array(value: Any, path: str) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise AcvpSchemaError("invalid_type", "Expected array", path)
    if not value:
        raise AcvpSchemaError("invalid_value", "Array must not be empty", path)
    result: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        result.append(require_object(item, child_path(path, index)))
    return result


def _uses_pre_hash(obj: Dict[str, Any]) -> bool:
    values = obj.get("preHash")
    return isinstance(values, list) and "preHash" in values
