from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from ...acvp_core.schema_error import AcvpSchemaError


_HEX_RE = re.compile(r"^[0-9A-Fa-f]*$")


def child_path(path: str, child: object) -> str:
    if isinstance(child, int):
        return f"{path}[{child}]"
    return f"{path}.{child}" if path else f"$.{child}"


def require_object(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AcvpSchemaError("invalid_type", "Expected object", path)
    return value


def require_array(value: Any, path: str, non_empty: bool = False) -> List[Any]:
    if not isinstance(value, list):
        raise AcvpSchemaError("invalid_type", "Expected array", path)
    if non_empty and not value:
        raise AcvpSchemaError("invalid_value", "Array must not be empty", path)
    return value


def require_string(value: Any, path: str, non_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise AcvpSchemaError("invalid_type", "Expected string", path)
    if non_empty and not value:
        raise AcvpSchemaError("invalid_value", "String must not be empty", path)
    return value


def require_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AcvpSchemaError("invalid_type", "Expected integer", path)
    return value


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise AcvpSchemaError("invalid_type", "Expected boolean", path)
    return value


def require_field(obj: Dict[str, Any], field: str, path: str) -> Any:
    if field not in obj:
        raise AcvpSchemaError(
            "missing_required_field",
            f"Missing required field: {field}",
            child_path(path, field),
        )
    return obj[field]


def require_absent(obj: Dict[str, Any], field: str, path: str, reason: str) -> None:
    if field in obj:
        raise AcvpSchemaError(
            "invalid_conditional_field",
            f"Field {field} is not allowed when {reason}",
            child_path(path, field),
        )


def require_allowed_fields(obj: Dict[str, Any], allowed: Set[str], path: str) -> None:
    for field in obj:
        if field not in allowed:
            raise AcvpSchemaError(
                "unknown_field",
                f"Unknown field: {field}",
                child_path(path, field),
            )


def require_hex_string(
    value: Any,
    path: str,
    *,
    allow_empty: bool = True,
    exact_bytes: Optional[int] = None,
) -> str:
    text = require_string(value, path)
    if not allow_empty and not text:
        raise AcvpSchemaError("invalid_hex", "Hex string must not be empty", path)
    if len(text) % 2:
        raise AcvpSchemaError(
            "invalid_hex",
            "Hex string must have an even number of characters",
            path,
        )
    if _HEX_RE.fullmatch(text) is None:
        raise AcvpSchemaError("invalid_hex", "Value must contain only hex characters", path)
    if exact_bytes is not None and len(text) != exact_bytes * 2:
        raise AcvpSchemaError(
            "invalid_length",
            f"Hex string must be exactly {exact_bytes} bytes",
            path,
        )
    return text.upper()


def require_enum(
    value: Any,
    allowed: Set[str],
    path: str,
    *,
    code: str = "invalid_value",
) -> str:
    text = require_string(value, path)
    if text not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise AcvpSchemaError(
            code,
            f"Invalid value {text!r}; expected one of: {allowed_text}",
            path,
        )
    return text


def require_enum_array(
    value: Any,
    allowed: Set[str],
    path: str,
    *,
    non_empty: bool = True,
    code: str = "invalid_value",
) -> List[str]:
    values = require_array(value, path, non_empty=non_empty)
    result: List[str] = []
    seen: Set[str] = set()
    for index, item in enumerate(values):
        item_path = child_path(path, index)
        normalized = require_enum(item, allowed, item_path, code=code)
        if normalized in seen:
            raise AcvpSchemaError(
                "duplicate_value",
                f"Duplicate value: {normalized}",
                item_path,
            )
        seen.add(normalized)
        result.append(normalized)
    return result


def validate_unique_int_ids(items: Sequence[Any], id_field: str, path: str) -> None:
    seen: Set[int] = set()
    duplicate_code = "duplicate_tgId" if id_field == "tgId" else "duplicate_tcId"
    for index, item in enumerate(items):
        item_path = child_path(path, index)
        obj = require_object(item, item_path)
        id_path = child_path(item_path, id_field)
        identifier = require_int(require_field(obj, id_field, item_path), id_path)
        if identifier in seen:
            raise AcvpSchemaError(
                duplicate_code,
                f"Duplicate {id_field}: {identifier}",
                id_path,
            )
        seen.add(identifier)


def validate_prereq_vals(obj: Dict[str, Any], path: str) -> None:
    if "prereqVals" not in obj:
        return
    prereq_path = child_path(path, "prereqVals")
    prereqs = require_array(obj["prereqVals"], prereq_path)
    for index, item in enumerate(prereqs):
        item_path = child_path(prereq_path, index)
        prereq = require_object(item, item_path)
        require_allowed_fields(prereq, {"algorithm", "valValue"}, item_path)
        require_string(
            require_field(prereq, "algorithm", item_path),
            child_path(item_path, "algorithm"),
            non_empty=True,
        )
        require_string(
            require_field(prereq, "valValue", item_path),
            child_path(item_path, "valValue"),
            non_empty=True,
        )
