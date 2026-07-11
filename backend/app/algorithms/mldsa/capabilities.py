from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ...acvp_core.schema_error import AcvpSchemaError
from .common import (
    child_path,
    require_array,
    require_field,
    require_object,
    require_string,
)
from .constants import (
    ALGORITHM,
    HASH_ALGORITHMS,
    MODES,
    PARAMETER_SETS,
    PRE_HASH_VALUES,
    REVISION,
    SIGNATURE_INTERFACES,
)
from .validators import validate_mldsa_registration


SUPPORTED_MLDSA_PARAMETER_SETS = ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]
SUPPORTED_MLDSA_MODES = ["keyGen", "sigGen", "sigVer"]
SUPPORTED_SIGNATURE_INTERFACES = ["internal", "external"]
SUPPORTED_PRE_HASH = ["pure", "preHash"]
SUPPORTED_HASH_ALGS_FOR_GENERATION = [
    value
    for value in (
        "SHA2-224",
        "SHA2-256",
        "SHA2-384",
        "SHA2-512",
        "SHA2-512/224",
        "SHA2-512/256",
        "SHA3-224",
        "SHA3-256",
        "SHA3-384",
        "SHA3-512",
        "SHAKE-128",
        "SHAKE-256",
    )
    if value in HASH_ALGORITHMS
]

_SUPPORTED_PARAMETER_SET_SET = set(SUPPORTED_MLDSA_PARAMETER_SETS)
_SUPPORTED_MODE_SET = set(SUPPORTED_MLDSA_MODES)
_SUPPORTED_SIGNATURE_INTERFACE_SET = set(SUPPORTED_SIGNATURE_INTERFACES)
_SUPPORTED_PRE_HASH_SET = set(SUPPORTED_PRE_HASH)
_SUPPORTED_HASH_ALG_SET = set(SUPPORTED_HASH_ALGS_FOR_GENERATION)

NEXT_VECTOR_GENERATION_ACTION = "NIST GenVal vector generation is available for negotiated capabilities."
def is_registration_container(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("algorithms"), list)


def validate_registration_container(payload: Any) -> Dict[str, Any]:
    obj = require_object(payload, "$")
    algorithms = require_array(
        require_field(obj, "algorithms", "$"),
        "$.algorithms",
        non_empty=True,
    )

    normalized_algorithms: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str]] = set()

    for index, item in enumerate(algorithms):
        item_path = child_path("$.algorithms", index)
        require_object(item, item_path)
        try:
            normalized = validate_mldsa_registration(item)
        except AcvpSchemaError as exc:
            raise _with_algorithm_path(exc, item_path) from exc

        algorithm = normalized.get("algorithm")
        mode = normalized.get("mode")
        revision = normalized.get("revision")
        _require_supported_registration_identity(algorithm, mode, revision, item_path)

        key = (str(algorithm), str(mode), str(revision))
        if key in seen:
            raise AcvpSchemaError(
                "duplicate_registration",
                "Duplicate algorithm/mode/revision registration.",
                child_path(item_path, "mode"),
            )
        seen.add(key)
        normalized_algorithms.append(normalized)

    container: Dict[str, Any] = {"algorithms": normalized_algorithms}
    if "label" in obj:
        container["label"] = require_string(obj["label"], "$.label")
    if "metadata" in obj:
        metadata = obj["metadata"]
        if not isinstance(metadata, (dict, list)):
            raise AcvpSchemaError(
                "invalid_type",
                "metadata must be a JSON object or array when provided",
                "$.metadata",
            )
        container["metadata"] = metadata
    return container


def negotiate_mldsa_capabilities(container: Dict[str, Any]) -> Dict[str, Any]:
    negotiated: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for registration in container["algorithms"]:
        mode = registration["mode"]
        if mode == "keyGen":
            result = _negotiate_keygen(registration, unsupported)
        elif mode == "sigGen":
            result = _negotiate_signature_mode(registration, unsupported, warnings)
        elif mode == "sigVer":
            result = _negotiate_signature_mode(registration, unsupported, warnings)
        else:
            result = None
            unsupported.append(
                _unsupported_entry(mode, "mode", mode, "Unsupported ML-DSA mode.")
            )

        if result is not None:
            negotiated.append(result)

    if not negotiated:
        raise AcvpSchemaError(
            "UNSUPPORTED_CAPABILITIES",
            "No supported ML-DSA capabilities were negotiated.",
            "$.algorithms",
        )

    return {
        "algorithm": ALGORITHM,
        "revision": REVISION,
        "negotiated": negotiated,
        "unsupported": unsupported,
        "warnings": warnings,
        "nextAction": NEXT_VECTOR_GENERATION_ACTION,
    }


def _require_supported_registration_identity(
    algorithm: Any,
    mode: Any,
    revision: Any,
    path: str,
) -> None:
    if algorithm != ALGORITHM:
        raise AcvpSchemaError(
            "unsupported_algorithm",
            f"Unsupported algorithm: {algorithm}",
            child_path(path, "algorithm"),
        )
    if revision != REVISION:
        raise AcvpSchemaError(
            "unsupported_revision",
            f"Unsupported revision: {revision}",
            child_path(path, "revision"),
        )
    if mode not in MODES or mode not in _SUPPORTED_MODE_SET:
        raise AcvpSchemaError(
            "invalid_mode",
            f"Unsupported ML-DSA mode: {mode}",
            child_path(path, "mode"),
        )


def _negotiate_keygen(
    registration: Dict[str, Any],
    unsupported: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parameter_sets = _ordered_intersection(
        registration.get("parameterSets", []),
        SUPPORTED_MLDSA_PARAMETER_SETS,
    )
    _append_unsupported_values(
        unsupported,
        registration["mode"],
        "parameterSets",
        registration.get("parameterSets", []),
        _SUPPORTED_PARAMETER_SET_SET,
        "Parameter set is not supported by the NIST GenVal ML-DSA module.",
    )
    if not parameter_sets:
        return None

    return {
        "mode": "keyGen",
        "parameterSets": parameter_sets,
        "status": "accepted",
    }


def _negotiate_signature_mode(
    registration: Dict[str, Any],
    unsupported: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    mode = registration["mode"]
    signature_interfaces = _ordered_intersection(
        registration.get("signatureInterfaces", []),
        SUPPORTED_SIGNATURE_INTERFACES,
    )
    _append_unsupported_values(
        unsupported,
        mode,
        "signatureInterfaces",
        registration.get("signatureInterfaces", []),
        _SUPPORTED_SIGNATURE_INTERFACE_SET,
        "Signature interface is not supported by the NIST GenVal ML-DSA module.",
    )

    pre_hash = []
    if "external" in signature_interfaces:
        pre_hash = _ordered_intersection(
            registration.get("preHash", []),
            SUPPORTED_PRE_HASH,
        )
        _append_unsupported_values(
            unsupported,
            mode,
            "preHash",
            registration.get("preHash", []),
            _SUPPORTED_PRE_HASH_SET,
            "preHash value is not supported by the NIST GenVal ML-DSA module.",
        )

    external_mu = []
    if "internal" in signature_interfaces:
        external_mu = _ordered_bool_intersection(registration.get("externalMu", []))
        if not external_mu:
            signature_interfaces = [
                value for value in signature_interfaces if value != "internal"
            ]

    capabilities, hash_algs = _negotiate_capabilities(
        registration,
        pre_hash,
        unsupported,
        warnings,
    )
    if not capabilities:
        return None

    if "preHash" in pre_hash and not hash_algs:
        pre_hash = [value for value in pre_hash if value != "preHash"]
        unsupported.append(
            _unsupported_entry(
                mode,
                "hashAlgs",
                "preHash",
                "preHash was requested but no hashAlg is supported for generation.",
                "Review ML-DSA module capability support.",
            )
        )
    if "external" in signature_interfaces and not pre_hash:
        signature_interfaces = [
            value for value in signature_interfaces if value != "external"
        ]
    if not signature_interfaces:
        return None

    parameter_sets = _ordered_unique(
        value
        for capability in capabilities
        for value in capability["parameterSets"]
    )
    message_length = _ordered_unique_domains(
        domain
        for capability in capabilities
        for domain in capability["messageLength"]
    )
    context_length = _ordered_unique_domains(
        domain
        for capability in capabilities
        for domain in capability["contextLength"]
    )

    result: Dict[str, Any] = {
        "mode": mode,
        "parameterSets": parameter_sets,
        "signatureInterfaces": signature_interfaces,
        "messageLength": message_length,
        "contextLength": context_length,
        "capabilities": capabilities,
        "status": "accepted",
    }
    if mode == "sigGen":
        result["deterministic"] = _ordered_bool_intersection(
            registration.get("deterministic", [])
        )
    if "internal" in signature_interfaces:
        result["externalMu"] = external_mu
    if "external" in signature_interfaces:
        result["preHash"] = pre_hash
    if hash_algs:
        result["hashAlgs"] = hash_algs
    return result


def _negotiate_capabilities(
    registration: Dict[str, Any],
    pre_hash: Sequence[str],
    unsupported: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    mode = registration["mode"]
    negotiated_capabilities: List[Dict[str, Any]] = []
    negotiated_hash_algs: List[str] = []

    for capability in registration.get("capabilities", []):
        parameter_sets = _ordered_intersection(
            capability.get("parameterSets", []),
            SUPPORTED_MLDSA_PARAMETER_SETS,
        )
        _append_unsupported_values(
            unsupported,
            mode,
            "parameterSets",
            capability.get("parameterSets", []),
            _SUPPORTED_PARAMETER_SET_SET,
            "Parameter set is not supported by the NIST GenVal ML-DSA module.",
        )
        if not parameter_sets:
            continue

        capability_entry: Dict[str, Any] = {
            "parameterSets": parameter_sets,
            "messageLength": list(capability.get("messageLength", [])),
            "contextLength": list(capability.get("contextLength", [])),
        }

        hash_algs = _negotiate_hash_algs(
            mode,
            capability.get("hashAlgs", []),
            unsupported,
            warnings,
        )
        if hash_algs:
            capability_entry["hashAlgs"] = hash_algs
            negotiated_hash_algs.extend(hash_algs)
        elif "preHash" in pre_hash and "pure" not in pre_hash:
            continue

        negotiated_capabilities.append(capability_entry)

    return negotiated_capabilities, _ordered_unique(negotiated_hash_algs)


def _negotiate_hash_algs(
    mode: str,
    values: Sequence[Any],
    unsupported: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> List[str]:
    del warnings
    negotiated: List[str] = []
    for value in values:
        if value in _SUPPORTED_HASH_ALG_SET and value not in negotiated:
            negotiated.append(str(value))
            continue
        entry = _unsupported_entry(
            mode,
            "hashAlgs",
            value,
            "Hash algorithm is not supported by the NIST GenVal ML-DSA module.",
            "Review ML-DSA module capability support.",
        )
        if entry not in unsupported:
            unsupported.append(entry)
    return negotiated


def _append_unsupported_values(
    unsupported: List[Dict[str, Any]],
    mode: str,
    field: str,
    values: Sequence[Any],
    supported: Set[Any],
    reason: str,
) -> None:
    for value in values:
        if value in supported:
            continue
        entry = _unsupported_entry(mode, field, value, reason)
        if entry not in unsupported:
            unsupported.append(entry)


def _unsupported_entry(
    mode: str,
    field: str,
    value: Any,
    reason: str,
    next_phase: str = "Review algorithm module capability support.",
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "field": field,
        "value": value,
        "reason": reason,
        "nextPhase": next_phase,
    }


def _ordered_intersection(values: Sequence[Any], allowed_order: Sequence[str]) -> List[str]:
    value_set = set(values)
    return [value for value in allowed_order if value in value_set]


def _ordered_bool_intersection(values: Sequence[Any]) -> List[bool]:
    result: List[bool] = []
    for value in (True, False):
        if value in values:
            result.append(value)
    return result


def _ordered_unique(values: Sequence[Any]) -> List[Any]:
    result: List[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _ordered_unique_domains(values: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen: Set[Tuple[Any, Any, Any]] = set()
    for domain in values:
        key = (domain.get("min"), domain.get("max"), domain.get("increment"))
        if key in seen:
            continue
        seen.add(key)
        result.append(domain)
    return result


def _with_algorithm_path(exc: AcvpSchemaError, prefix: str) -> AcvpSchemaError:
    if not exc.path or exc.path == "$":
        path = prefix
    elif exc.path.startswith("$."):
        path = f"{prefix}{exc.path[1:]}"
    else:
        path = exc.path
    return AcvpSchemaError(exc.code, exc.message, path)
