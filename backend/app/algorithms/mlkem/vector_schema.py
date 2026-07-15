from __future__ import annotations

from typing import Any, Dict, List

from ...acvp_core.schema_error import AcvpSchemaError
from .common import (
    child_path,
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
    CIPHERTEXT_BYTES,
    D_BYTES,
    DECAPSULATION_KEY_BYTES,
    ENCAPSULATION_KEY_BYTES,
    FUNCTIONS,
    FUNCTION_TEST_TYPES,
    M_BYTES,
    MODES,
    PARAMETER_SETS,
    REVISION,
    Z_BYTES,
)
from .normalize import normalize_acvp_container


_TOP_LEVEL_FIELDS = {
    "acvVersion",
    "vsId",
    "algorithm",
    "mode",
    "revision",
    "isSample",
    "testGroups",
}


def validate_vector_set(payload: Any) -> Dict[str, Any]:
    obj = require_object(normalize_acvp_container(payload), "$")
    mode = _validate_top_level(obj)
    groups = require_field(obj, "testGroups", "$")
    _validate_groups(groups, mode)
    return obj


def _validate_top_level(obj: Dict[str, Any]) -> str:
    require_allowed_fields(obj, _TOP_LEVEL_FIELDS, "$")
    require_int(require_field(obj, "vsId", "$"), "$.vsId")
    algorithm = require_string(require_field(obj, "algorithm", "$"), "$.algorithm")
    if algorithm != ALGORITHM:
        raise AcvpSchemaError(
            "unsupported_algorithm",
            f"Unsupported algorithm: {algorithm}",
            "$.algorithm",
        )
    mode = require_enum(
        require_field(obj, "mode", "$"),
        MODES,
        "$.mode",
        code="invalid_mode",
    )
    revision = require_string(require_field(obj, "revision", "$"), "$.revision")
    if revision != REVISION:
        raise AcvpSchemaError(
            "unsupported_revision",
            f"Unsupported revision: {revision}",
            "$.revision",
        )
    if obj.get("acvVersion") is not None:
        require_string(obj["acvVersion"], "$.acvVersion")
    if "isSample" in obj:
        require_bool(obj["isSample"], "$.isSample")
    return mode


def _validate_groups(value: Any, mode: str) -> None:
    if not isinstance(value, list):
        raise AcvpSchemaError("invalid_type", "Expected array", "$.testGroups")
    if not value:
        raise AcvpSchemaError("invalid_value", "Array must not be empty", "$.testGroups")
    validate_unique_int_ids(value, "tgId", "$.testGroups")
    all_tests: List[Any] = []

    for group_index, item in enumerate(value):
        group_path = child_path("$.testGroups", group_index)
        group = require_object(item, group_path)
        if mode == "keyGen":
            _validate_keygen_group(group, group_path)
        else:
            _validate_encap_decap_group(group, group_path)
        tests = require_field(group, "tests", group_path)
        all_tests.extend(tests)
    validate_unique_int_ids(all_tests, "tcId", "$.testGroups[*].tests")


def _validate_common_group(group: Dict[str, Any], path: str) -> tuple[str, List[Any]]:
    require_int(require_field(group, "tgId", path), child_path(path, "tgId"))
    parameter_set = require_enum(
        require_field(group, "parameterSet", path),
        PARAMETER_SETS,
        child_path(path, "parameterSet"),
        code="invalid_parameter_set",
    )
    tests = require_field(group, "tests", path)
    if not isinstance(tests, list):
        raise AcvpSchemaError("invalid_type", "Expected array", child_path(path, "tests"))
    if not tests:
        raise AcvpSchemaError(
            "invalid_value",
            "Array must not be empty",
            child_path(path, "tests"),
        )
    return parameter_set, tests


def _validate_keygen_group(group: Dict[str, Any], path: str) -> None:
    require_allowed_fields(group, {"tgId", "testType", "parameterSet", "tests"}, path)
    test_type = require_string(
        require_field(group, "testType", path),
        child_path(path, "testType"),
    )
    if test_type != FUNCTION_TEST_TYPES["keyGen"]:
        raise AcvpSchemaError(
            "invalid_test_type",
            "keyGen testType must be AFT",
            child_path(path, "testType"),
        )
    _, tests = _validate_common_group(group, path)
    for index, item in enumerate(tests):
        test_path = child_path(child_path(path, "tests"), index)
        test = require_object(item, test_path)
        require_allowed_fields(test, {"tcId", "d", "z"}, test_path)
        require_int(require_field(test, "tcId", test_path), child_path(test_path, "tcId"))
        test["d"] = require_hex_string(
            require_field(test, "d", test_path),
            child_path(test_path, "d"),
            allow_empty=False,
            exact_bytes=D_BYTES,
        )
        test["z"] = require_hex_string(
            require_field(test, "z", test_path),
            child_path(test_path, "z"),
            allow_empty=False,
            exact_bytes=Z_BYTES,
        )


def _validate_encap_decap_group(group: Dict[str, Any], path: str) -> None:
    require_allowed_fields(
        group,
        {"tgId", "testType", "parameterSet", "function", "tests"},
        path,
    )
    parameter_set, tests = _validate_common_group(group, path)
    function = require_enum(
        require_field(group, "function", path),
        FUNCTIONS,
        child_path(path, "function"),
        code="invalid_function",
    )
    test_type = require_string(
        require_field(group, "testType", path),
        child_path(path, "testType"),
    )
    expected_test_type = FUNCTION_TEST_TYPES[function]
    if test_type != expected_test_type:
        raise AcvpSchemaError(
            "invalid_test_type",
            f"{function} testType must be {expected_test_type}",
            child_path(path, "testType"),
        )
    for index, item in enumerate(tests):
        test_path = child_path(child_path(path, "tests"), index)
        test = require_object(item, test_path)
        _validate_encap_decap_test(test, test_path, parameter_set, function)


def _validate_encap_decap_test(
    test: Dict[str, Any],
    path: str,
    parameter_set: str,
    function: str,
) -> None:
    fields = {
        "encapsulation": {"tcId", "ek", "m"},
        "decapsulation": {"tcId", "dk", "c"},
        "encapsulationKeyCheck": {"tcId", "ek"},
        "decapsulationKeyCheck": {"tcId", "dk"},
    }[function]
    require_allowed_fields(test, fields, path)
    require_int(require_field(test, "tcId", path), child_path(path, "tcId"))

    if function == "encapsulation":
        test["ek"] = require_hex_string(
            require_field(test, "ek", path),
            child_path(path, "ek"),
            allow_empty=False,
            exact_bytes=ENCAPSULATION_KEY_BYTES[parameter_set],
        )
        test["m"] = require_hex_string(
            require_field(test, "m", path),
            child_path(path, "m"),
            allow_empty=False,
            exact_bytes=M_BYTES,
        )
    elif function == "decapsulation":
        test["dk"] = require_hex_string(
            require_field(test, "dk", path),
            child_path(path, "dk"),
            allow_empty=False,
            exact_bytes=DECAPSULATION_KEY_BYTES[parameter_set],
        )
        test["c"] = require_hex_string(
            require_field(test, "c", path),
            child_path(path, "c"),
            allow_empty=False,
            exact_bytes=CIPHERTEXT_BYTES[parameter_set],
        )
    elif function == "encapsulationKeyCheck":
        test["ek"] = require_hex_string(
            require_field(test, "ek", path),
            child_path(path, "ek"),
            allow_empty=False,
        )
    else:
        test["dk"] = require_hex_string(
            require_field(test, "dk", path),
            child_path(path, "dk"),
            allow_empty=False,
        )
