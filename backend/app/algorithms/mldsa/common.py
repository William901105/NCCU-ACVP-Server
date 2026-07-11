from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

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


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise AcvpSchemaError("invalid_type", "Expected string", path)
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
    allow_empty: bool = True,
    exact_bytes: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> str:
    text = require_string(value, path)
    if not allow_empty and text == "":
        raise AcvpSchemaError("invalid_hex", "Hex string must not be empty", path)
    if len(text) % 2 != 0:
        raise AcvpSchemaError("invalid_hex", "Hex string must have an even number of characters", path)
    if _HEX_RE.fullmatch(text) is None:
        raise AcvpSchemaError("invalid_hex", "Value must contain only hex characters", path)
    if exact_bytes is not None and len(text) != exact_bytes * 2:
        raise AcvpSchemaError(
            "invalid_hex",
            f"Hex string must be exactly {exact_bytes} bytes",
            path,
        )
    if max_bytes is not None and len(text) > max_bytes * 2:
        raise AcvpSchemaError(
            "invalid_hex",
            f"Hex string must be at most {max_bytes} bytes",
            path,
        )
    return text.upper()


def require_enum(value: Any, allowed: Set[str], path: str, code: str = "invalid_value") -> str:
    text = require_string(value, path)
    if text not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise AcvpSchemaError(code, f"Invalid value {text!r}; expected one of: {allowed_text}", path)
    return text


def validate_unique_int_ids(items: Sequence[Any], id_field: str, path: str) -> None:
    seen: Set[int] = set()
    duplicate_code = "duplicate_tgId" if id_field == "tgId" else "duplicate_tcId"
    for index, item in enumerate(items):
        item_obj = require_object(item, child_path(path, index))
        item_path = child_path(child_path(path, index), id_field)
        identifier = require_int(require_field(item_obj, id_field, child_path(path, index)), item_path)
        if identifier in seen:
            raise AcvpSchemaError(
                duplicate_code,
                f"Duplicate {id_field}: {identifier}",
                item_path,
            )
        seen.add(identifier)


def require_enum_array(
    value: Any,
    allowed: Set[str],
    path: str,
    non_empty: bool = True,
    code: str = "invalid_value",
) -> List[str]:
    array = require_array(value, path, non_empty=non_empty)
    result: List[str] = []
    for index, item in enumerate(array):
        result.append(require_enum(item, allowed, child_path(path, index), code=code))
    return result


def require_bool_array(value: Any, path: str, non_empty: bool = True) -> List[bool]:
    array = require_array(value, path, non_empty=non_empty)
    result: List[bool] = []
    for index, item in enumerate(array):
        result.append(require_bool(item, child_path(path, index)))
    return result


def validate_domain_list(
    value: Any,
    path: str,
    constraints: Tuple[int, int, int],
    non_empty: bool = True,
) -> List[Dict[str, int]]:
    minimum_allowed, maximum_allowed, increment_allowed = constraints
    array = require_array(value, path, non_empty=non_empty)
    domains: List[Dict[str, int]] = []

    for index, item in enumerate(array):
        item_path = child_path(path, index)
        obj = require_object(item, item_path)
        minimum = require_int(require_field(obj, "min", item_path), child_path(item_path, "min"))
        maximum = require_int(require_field(obj, "max", item_path), child_path(item_path, "max"))
        increment = require_int(require_field(obj, "increment", item_path), child_path(item_path, "increment"))

        if minimum < minimum_allowed or maximum > maximum_allowed:
            raise AcvpSchemaError(
                "invalid_value",
                f"Domain must stay within {minimum_allowed}..{maximum_allowed}",
                item_path,
            )
        if minimum > maximum:
            raise AcvpSchemaError("invalid_value", "Domain min must be <= max", item_path)
        if increment <= 0 or increment % increment_allowed != 0:
            raise AcvpSchemaError(
                "invalid_value",
                f"Domain increment must be a positive multiple of {increment_allowed}",
                child_path(item_path, "increment"),
            )
        if minimum % increment_allowed != 0 or maximum % increment_allowed != 0:
            raise AcvpSchemaError(
                "invalid_value",
                f"Domain min/max must align to {increment_allowed}-bit increments",
                item_path,
            )
        domains.append({"min": minimum, "max": maximum, "increment": increment})

    return domains


def require_optional_string(obj: Dict[str, Any], field: str, path: str) -> Optional[str]:
    if field not in obj:
        return None
    return require_string(obj[field], child_path(path, field))


def validate_prereq_vals(obj: Dict[str, Any], path: str) -> None:
    if "prereqVals" not in obj:
        return
    prereqs = require_array(obj["prereqVals"], child_path(path, "prereqVals"))
    for index, item in enumerate(prereqs):
        item_path = child_path(child_path(path, "prereqVals"), index)
        prereq = require_object(item, item_path)
        require_string(require_field(prereq, "algorithm", item_path), child_path(item_path, "algorithm"))
        require_string(require_field(prereq, "valValue", item_path), child_path(item_path, "valValue"))


def first_present_field(test: Dict[str, Any], fields: Iterable[str]) -> Optional[str]:
    for field in fields:
        if field in test:
            return field
    return None
