from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import (
    child_path,
    first_present_field,
    require_allowed_fields,
    require_bool,
    require_enum,
    require_field,
    require_hex_string,
    require_int,
    require_object,
    require_string,
    validate_unique_int_ids,
)
from .constants import (
    ALGORITHM,
    MODES,
    PUBLIC_KEY_BYTES,
    REVISION,
    SECRET_KEY_BYTES,
    SIGNATURE_BYTES,
)
from ...acvp_core.schema_error import AcvpSchemaError
from .normalize import normalize_acvp_container


_RESPONSE_TOP_LEVEL_FIELDS = {
    "acvVersion",
    "vsId",
    "algorithm",
    "mode",
    "revision",
    "isSample",
    "testGroups",
    "extensions",
}


def validate_response(payload: Any, expected_mode: Optional[str] = None) -> Dict[str, Any]:
    obj = require_object(normalize_acvp_container(payload), "$")
    mode = _validate_common_response(obj, "$", expected_mode)
    test_groups = require_field(obj, "testGroups", "$")
    _validate_response_groups(test_groups, "$.testGroups", mode)
    return obj


def _validate_common_response(obj: Dict[str, Any], path: str, expected_mode: Optional[str]) -> str:
    require_allowed_fields(obj, _RESPONSE_TOP_LEVEL_FIELDS, path)
    require_int(require_field(obj, "vsId", path), child_path(path, "vsId"))
    if "extensions" in obj:
        require_object(obj["extensions"], child_path(path, "extensions"))

    if "algorithm" in obj:
        algorithm = require_string(obj["algorithm"], child_path(path, "algorithm"))
        if algorithm != ALGORITHM:
            raise AcvpSchemaError(
                "unsupported_algorithm",
                f"Unsupported algorithm: {algorithm}",
                child_path(path, "algorithm"),
            )

    if "revision" in obj:
        revision = require_string(obj["revision"], child_path(path, "revision"))
        if revision != REVISION:
            raise AcvpSchemaError(
                "unsupported_revision",
                f"Unsupported revision: {revision}",
                child_path(path, "revision"),
            )

    if expected_mode is not None:
        return require_enum(expected_mode, MODES, "$.expected_mode", code="invalid_mode")

    if "mode" in obj:
        return require_enum(obj["mode"], MODES, child_path(path, "mode"), code="invalid_mode")

    return _infer_response_mode(obj)


def _validate_response_groups(value: Any, path: str, mode: str) -> None:
    if not isinstance(value, list):
        raise AcvpSchemaError("invalid_type", "Expected array", path)
    if not value:
        raise AcvpSchemaError("invalid_value", "Array must not be empty", path)

    validate_unique_int_ids(value, "tgId", path)
    all_tests: List[Any] = []

    for group_index, item in enumerate(value):
        group_path = child_path(path, group_index)
        group = require_object(item, group_path)
        require_allowed_fields(group, {"tgId", "tests"}, group_path)
        require_int(require_field(group, "tgId", group_path), child_path(group_path, "tgId"))
        tests = require_field(group, "tests", group_path)
        if not isinstance(tests, list):
            raise AcvpSchemaError("invalid_type", "Expected array", child_path(group_path, "tests"))
        if not tests:
            raise AcvpSchemaError("invalid_value", "Array must not be empty", child_path(group_path, "tests"))
        for test_index, test_item in enumerate(tests):
            test_path = child_path(child_path(group_path, "tests"), test_index)
            test = require_object(test_item, test_path)
            _validate_response_test(test, test_path, mode)
        all_tests.extend(tests)

    validate_unique_int_ids(all_tests, "tcId", "$.testGroups[*].tests")


def _validate_response_test(test: Dict[str, Any], path: str, mode: str) -> None:
    require_int(require_field(test, "tcId", path), child_path(path, "tcId"))
    if mode == "keyGen":
        require_allowed_fields(test, {"tcId", "pk", "sk"}, path)
        pk = require_hex_string(require_field(test, "pk", path), child_path(path, "pk"), allow_empty=False)
        sk = require_hex_string(require_field(test, "sk", path), child_path(path, "sk"), allow_empty=False)
        pk_parameter_set = _parameter_set_for_length(
            PUBLIC_KEY_BYTES,
            len(pk) // 2,
            child_path(path, "pk"),
            "public key",
        )
        sk_parameter_set = _parameter_set_for_length(
            SECRET_KEY_BYTES,
            len(sk) // 2,
            child_path(path, "sk"),
            "secret key",
        )
        if pk_parameter_set != sk_parameter_set:
            raise AcvpSchemaError(
                "invalid_length",
                "pk and sk lengths must correspond to the same parameterSet",
                path,
            )
    elif mode == "sigGen":
        require_allowed_fields(test, {"tcId", "signature"}, path)
        signature = require_hex_string(
            require_field(test, "signature", path),
            child_path(path, "signature"),
            allow_empty=False,
        )
        _parameter_set_for_length(
            SIGNATURE_BYTES,
            len(signature) // 2,
            child_path(path, "signature"),
            "signature",
        )
    elif mode == "sigVer":
        require_allowed_fields(test, {"tcId", "testPassed"}, path)
        require_bool(require_field(test, "testPassed", path), child_path(path, "testPassed"))
    else:
        raise AcvpSchemaError("invalid_mode", f"Unsupported mode: {mode}", path)


def _parameter_set_for_length(
    sizes: Dict[str, int],
    actual_bytes: int,
    path: str,
    label: str,
) -> str:
    for parameter_set, expected_bytes in sizes.items():
        if actual_bytes == expected_bytes:
            return parameter_set
    expected = ", ".join(
        f"{parameter_set}={expected_bytes}"
        for parameter_set, expected_bytes in sorted(sizes.items())
    )
    raise AcvpSchemaError(
        "invalid_length",
        f"{label} length must match a supported parameterSet ({expected})",
        path,
    )


def _infer_response_mode(obj: Dict[str, Any]) -> str:
    groups = obj.get("testGroups")
    if not isinstance(groups, list):
        raise AcvpSchemaError("invalid_mode", "Cannot infer response mode without testGroups", "$.testGroups")

    seen = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        tests = group.get("tests")
        if not isinstance(tests, list):
            continue
        for test in tests:
            if not isinstance(test, dict):
                continue
            field = first_present_field(test, ("pk", "sk", "signature", "testPassed"))
            if field in {"pk", "sk"}:
                seen.add("keyGen")
            elif field == "signature":
                seen.add("sigGen")
            elif field == "testPassed":
                seen.add("sigVer")

    if len(seen) == 1:
        return next(iter(seen))
    raise AcvpSchemaError(
        "invalid_mode",
        "Cannot infer response mode; provide expected_mode or a top-level mode field",
        "$.mode",
    )
