from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

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
    DECAPSULATION_KEY_BYTES,
    ENCAPSULATION_KEY_BYTES,
    K_BYTES,
    MODES,
    REVISION,
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
    "extensions",
}
_ENCAP_DECAP_SHAPES = {
    frozenset({"c", "k"}),
    frozenset({"k"}),
    frozenset({"testPassed"}),
}


def validate_response(payload: Any, expected_mode: Optional[str] = None) -> Dict[str, Any]:
    obj = require_object(normalize_acvp_container(payload), "$")
    mode = _validate_top_level(obj, expected_mode)
    _validate_groups(require_field(obj, "testGroups", "$"), mode)
    return obj


def _validate_top_level(obj: Dict[str, Any], expected_mode: Optional[str]) -> str:
    require_allowed_fields(obj, _TOP_LEVEL_FIELDS, "$")
    require_int(require_field(obj, "vsId", "$"), "$.vsId")
    if obj.get("acvVersion") is not None:
        require_string(obj["acvVersion"], "$.acvVersion")
    if "isSample" in obj:
        require_bool(obj["isSample"], "$.isSample")
    if "extensions" in obj:
        require_object(obj["extensions"], "$.extensions")

    if "algorithm" in obj:
        algorithm = require_string(obj["algorithm"], "$.algorithm")
        if algorithm != ALGORITHM:
            raise AcvpSchemaError(
                "unsupported_algorithm",
                f"Unsupported algorithm: {algorithm}",
                "$.algorithm",
            )
    if "revision" in obj:
        revision = require_string(obj["revision"], "$.revision")
        if revision != REVISION:
            raise AcvpSchemaError(
                "unsupported_revision",
                f"Unsupported revision: {revision}",
                "$.revision",
            )

    supplied_mode: Optional[str] = None
    if "mode" in obj:
        supplied_mode = require_enum(
            obj["mode"],
            MODES,
            "$.mode",
            code="invalid_mode",
        )
    if expected_mode is not None:
        mode = require_enum(
            expected_mode,
            MODES,
            "$.expected_mode",
            code="invalid_mode",
        )
        if supplied_mode is not None and supplied_mode != mode:
            raise AcvpSchemaError(
                "invalid_mode",
                f"Response mode {supplied_mode!r} does not match expected mode {mode!r}",
                "$.mode",
            )
        return mode
    return supplied_mode or _infer_mode(obj)


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
        require_allowed_fields(group, {"tgId", "tests"}, group_path)
        require_int(require_field(group, "tgId", group_path), child_path(group_path, "tgId"))
        tests = require_field(group, "tests", group_path)
        if not isinstance(tests, list):
            raise AcvpSchemaError("invalid_type", "Expected array", child_path(group_path, "tests"))
        if not tests:
            raise AcvpSchemaError(
                "invalid_value",
                "Array must not be empty",
                child_path(group_path, "tests"),
            )
        group_shape: Optional[frozenset[str]] = None
        for test_index, test_item in enumerate(tests):
            test_path = child_path(child_path(group_path, "tests"), test_index)
            test = require_object(test_item, test_path)
            shape = frozenset(field for field in test if field != "tcId")
            if group_shape is None:
                group_shape = shape
            elif shape != group_shape:
                raise AcvpSchemaError(
                    "mixed_response_shapes",
                    "All tests in a response group must use the same response shape",
                    test_path,
                )
            _validate_test(test, test_path, mode, shape)
        all_tests.extend(tests)
    validate_unique_int_ids(all_tests, "tcId", "$.testGroups[*].tests")


def _validate_test(
    test: Dict[str, Any],
    path: str,
    mode: str,
    shape: frozenset[str],
) -> None:
    require_int(require_field(test, "tcId", path), child_path(path, "tcId"))
    if mode == "keyGen":
        require_allowed_fields(test, {"tcId", "ek", "dk"}, path)
        if shape != frozenset({"ek", "dk"}):
            raise AcvpSchemaError(
                "invalid_response_shape",
                "keyGen response tests must contain tcId, ek, and dk",
                path,
            )
        ek = require_hex_string(
            require_field(test, "ek", path),
            child_path(path, "ek"),
            allow_empty=False,
        )
        dk = require_hex_string(
            require_field(test, "dk", path),
            child_path(path, "dk"),
            allow_empty=False,
        )
        ek_set = _parameter_set_for_length(
            ENCAPSULATION_KEY_BYTES,
            len(ek) // 2,
            child_path(path, "ek"),
            "encapsulation key",
        )
        dk_set = _parameter_set_for_length(
            DECAPSULATION_KEY_BYTES,
            len(dk) // 2,
            child_path(path, "dk"),
            "decapsulation key",
        )
        if ek_set != dk_set:
            raise AcvpSchemaError(
                "invalid_length",
                "ek and dk lengths must correspond to the same parameterSet",
                path,
            )
        test["ek"], test["dk"] = ek, dk
        return

    if shape not in _ENCAP_DECAP_SHAPES:
        require_allowed_fields(test, {"tcId", "c", "k", "testPassed"}, path)
        raise AcvpSchemaError(
            "invalid_response_shape",
            "encapDecap response must use c+k, k, or testPassed shape",
            path,
        )
    require_allowed_fields(test, {"tcId", *shape}, path)
    if shape == frozenset({"c", "k"}):
        ciphertext = require_hex_string(
            require_field(test, "c", path),
            child_path(path, "c"),
            allow_empty=False,
        )
        _parameter_set_for_length(
            CIPHERTEXT_BYTES,
            len(ciphertext) // 2,
            child_path(path, "c"),
            "ciphertext",
        )
        test["c"] = ciphertext
        test["k"] = _validate_shared_secret(test, path)
    elif shape == frozenset({"k"}):
        test["k"] = _validate_shared_secret(test, path)
    else:
        test["testPassed"] = require_bool(
            require_field(test, "testPassed", path),
            child_path(path, "testPassed"),
        )


def _validate_shared_secret(test: Dict[str, Any], path: str) -> str:
    return require_hex_string(
        require_field(test, "k", path),
        child_path(path, "k"),
        allow_empty=False,
        exact_bytes=K_BYTES,
    )


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


def _infer_mode(obj: Dict[str, Any]) -> str:
    groups = obj.get("testGroups")
    if not isinstance(groups, list):
        raise AcvpSchemaError(
            "invalid_mode",
            "Cannot infer response mode without testGroups",
            "$.testGroups",
        )
    modes: Set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("tests"), list):
            continue
        for test in group["tests"]:
            if not isinstance(test, dict):
                continue
            shape = frozenset(field for field in test if field != "tcId")
            if shape == frozenset({"ek", "dk"}):
                modes.add("keyGen")
            elif shape in _ENCAP_DECAP_SHAPES:
                modes.add("encapDecap")
    if len(modes) == 1:
        return next(iter(modes))
    raise AcvpSchemaError(
        "invalid_mode",
        "Cannot infer response mode; provide expected_mode or a top-level mode field",
        "$.mode",
    )
