from __future__ import annotations

from typing import Any, Dict, List

from .common import (
    child_path,
    require_absent,
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
    CONTEXT_MAX_BYTES,
    HASH_ALGORITHMS,
    KEY_FORMATS,
    MODES,
    MU_BYTES,
    PARAMETER_SETS,
    PRE_HASH_VALUES,
    PUBLIC_KEY_BYTES,
    REVISION,
    REVISION_TR1,
    RND_BYTES,
    SECRET_KEY_BYTES,
    SEED_BYTES,
    SIGNATURE_INTERFACES,
    SIGNATURE_BYTES,
    TEST_TYPES,
)
from ...acvp_core.schema_error import AcvpSchemaError
from .normalize import normalize_acvp_container


def validate_vector_set(payload: Any, *, revision: str = REVISION) -> Dict[str, Any]:
    obj = require_object(normalize_acvp_container(payload), "$")
    mode = _validate_common_vector_set(obj, "$", revision)
    if revision == REVISION_TR1 and mode != "sigGen":
        raise AcvpSchemaError(
            "unsupported_mode_revision_combination",
            f"FIPS204-tr1 is only defined for ML-DSA sigGen, not {mode}",
            "$.mode",
        )
    test_groups = require_field(obj, "testGroups", "$")
    _validate_groups(test_groups, "$.testGroups", mode, revision)
    return obj


def _validate_common_vector_set(obj: Dict[str, Any], path: str, revision: str) -> str:
    require_allowed_fields(
        obj,
        {"acvVersion", "vsId", "algorithm", "mode", "revision", "isSample", "testGroups"},
        path,
    )
    require_int(require_field(obj, "vsId", path), child_path(path, "vsId"))
    algorithm = require_string(require_field(obj, "algorithm", path), child_path(path, "algorithm"))
    if algorithm != ALGORITHM:
        raise AcvpSchemaError("unsupported_algorithm", f"Unsupported algorithm: {algorithm}", child_path(path, "algorithm"))

    mode = require_enum(require_field(obj, "mode", path), MODES, child_path(path, "mode"), code="invalid_mode")

    actual_revision = require_string(require_field(obj, "revision", path), child_path(path, "revision"))
    if actual_revision != revision:
        raise AcvpSchemaError("unsupported_revision", f"Unsupported revision: {actual_revision}", child_path(path, "revision"))

    if "isSample" in obj:
        require_bool(obj["isSample"], child_path(path, "isSample"))
    return mode


def _validate_groups(value: Any, path: str, mode: str, revision: str) -> None:
    if not isinstance(value, list):
        raise AcvpSchemaError("invalid_type", "Expected array", path)
    if not value:
        raise AcvpSchemaError("invalid_value", "Array must not be empty", path)

    validate_unique_int_ids(value, "tgId", path)
    all_tests: List[Any] = []

    for group_index, item in enumerate(value):
        group_path = child_path(path, group_index)
        group = require_object(item, group_path)
        if mode == "keyGen":
            _validate_keygen_group(group, group_path)
        elif mode == "sigGen":
            _validate_siggen_group(group, group_path, revision=revision)
        elif mode == "sigVer":
            _validate_sigver_group(group, group_path)
        all_tests.extend(require_field(group, "tests", group_path))

    validate_unique_int_ids(all_tests, "tcId", "$.testGroups[*].tests")


def _validate_common_group(group: Dict[str, Any], path: str) -> tuple[str, List[Any]]:
    require_int(require_field(group, "tgId", path), child_path(path, "tgId"))
    require_enum(require_field(group, "testType", path), TEST_TYPES, child_path(path, "testType"))
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
        raise AcvpSchemaError("invalid_value", "Array must not be empty", child_path(path, "tests"))
    return parameter_set, tests


def _validate_keygen_group(group: Dict[str, Any], path: str) -> None:
    require_allowed_fields(group, {"tgId", "testType", "parameterSet", "tests"}, path)
    _, tests = _validate_common_group(group, path)
    for index, item in enumerate(tests):
        test_path = child_path(child_path(path, "tests"), index)
        test = require_object(item, test_path)
        require_allowed_fields(test, {"tcId", "seed"}, test_path)
        require_int(require_field(test, "tcId", test_path), child_path(test_path, "tcId"))
        require_hex_string(
            require_field(test, "seed", test_path),
            child_path(test_path, "seed"),
            allow_empty=False,
            exact_bytes=SEED_BYTES,
        )


def _validate_siggen_group(
    group: Dict[str, Any], path: str, *, revision: str = REVISION
) -> None:
    parameter_set, tests = _validate_common_group(group, path)
    key_format = "expanded"
    if revision == REVISION_TR1:
        key_format = require_enum(
            require_field(group, "keyFormat", path),
            KEY_FORMATS,
            child_path(path, "keyFormat"),
            code="invalid_key_format",
        )
    elif "keyFormat" in group:
        raise AcvpSchemaError(
            "invalid_conditional_field",
            "keyFormat is only valid for FIPS204-tr1 sigGen",
            child_path(path, "keyFormat"),
        )
    deterministic = require_bool(require_field(group, "deterministic", path), child_path(path, "deterministic"))
    signature_interface = require_enum(
        require_field(group, "signatureInterface", path),
        SIGNATURE_INTERFACES,
        child_path(path, "signatureInterface"),
    )

    external_mu = None
    pre_hash = None
    if signature_interface == "internal":
        require_allowed_fields(
            group,
            {
                "tgId",
                "testType",
                "parameterSet",
                "deterministic",
                "signatureInterface",
                "externalMu",
                *({"keyFormat"} if revision == REVISION_TR1 else set()),
                "tests",
            },
            path,
        )
        external_mu = require_bool(require_field(group, "externalMu", path), child_path(path, "externalMu"))
        require_absent(group, "preHash", path, "signatureInterface is internal")
    else:
        require_allowed_fields(
            group,
            {
                "tgId",
                "testType",
                "parameterSet",
                "deterministic",
                "signatureInterface",
                "preHash",
                *({"keyFormat"} if revision == REVISION_TR1 else set()),
                "tests",
            },
            path,
        )
        pre_hash = require_enum(require_field(group, "preHash", path), PRE_HASH_VALUES, child_path(path, "preHash"))
        require_absent(group, "externalMu", path, "signatureInterface is external")

    for index, item in enumerate(tests):
        test_path = child_path(child_path(path, "tests"), index)
        test = require_object(item, test_path)
        if signature_interface == "internal":
            key_field = "seed" if key_format == "seed" else "sk"
            allowed = {"tcId", key_field, "mu" if external_mu else "message"}
            if not deterministic:
                allowed.add("rnd")
            require_allowed_fields(test, allowed, test_path)
            _validate_common_siggen_test(
                test, test_path, deterministic, parameter_set, key_format
            )
            _validate_internal_message_or_mu(test, test_path, bool(external_mu))
        else:
            key_field = "seed" if key_format == "seed" else "sk"
            allowed = {"tcId", key_field, "message", "context"}
            if pre_hash == "preHash":
                allowed.add("hashAlg")
            if not deterministic:
                allowed.add("rnd")
            require_allowed_fields(test, allowed, test_path)
            _validate_common_siggen_test(
                test, test_path, deterministic, parameter_set, key_format
            )
            _validate_external_message(test, test_path, str(pre_hash))


def _validate_sigver_group(group: Dict[str, Any], path: str) -> None:
    parameter_set, tests = _validate_common_group(group, path)
    signature_interface = require_enum(
        require_field(group, "signatureInterface", path),
        SIGNATURE_INTERFACES,
        child_path(path, "signatureInterface"),
    )

    external_mu = None
    pre_hash = None
    if signature_interface == "internal":
        require_allowed_fields(
            group,
            {
                "tgId",
                "testType",
                "parameterSet",
                "signatureInterface",
                "externalMu",
                "tests",
            },
            path,
        )
        external_mu = require_bool(require_field(group, "externalMu", path), child_path(path, "externalMu"))
        require_absent(group, "preHash", path, "signatureInterface is internal")
    else:
        require_allowed_fields(
            group,
            {
                "tgId",
                "testType",
                "parameterSet",
                "signatureInterface",
                "preHash",
                "tests",
            },
            path,
        )
        pre_hash = require_enum(require_field(group, "preHash", path), PRE_HASH_VALUES, child_path(path, "preHash"))
        require_absent(group, "externalMu", path, "signatureInterface is external")

    for index, item in enumerate(tests):
        test_path = child_path(child_path(path, "tests"), index)
        test = require_object(item, test_path)
        if signature_interface == "internal":
            require_allowed_fields(
                test,
                {"tcId", "pk", "signature", "mu" if external_mu else "message"},
                test_path,
            )
        else:
            allowed = {"tcId", "pk", "message", "context", "signature"}
            if pre_hash == "preHash":
                allowed.add("hashAlg")
            require_allowed_fields(test, allowed, test_path)
        require_int(require_field(test, "tcId", test_path), child_path(test_path, "tcId"))
        require_hex_string(
            require_field(test, "pk", test_path),
            child_path(test_path, "pk"),
            allow_empty=False,
            exact_bytes=PUBLIC_KEY_BYTES[parameter_set],
        )
        require_hex_string(
            require_field(test, "signature", test_path),
            child_path(test_path, "signature"),
            allow_empty=False,
            exact_bytes=SIGNATURE_BYTES[parameter_set],
        )
        if signature_interface == "internal":
            _validate_internal_message_or_mu(test, test_path, bool(external_mu))
        else:
            _validate_external_message(test, test_path, str(pre_hash))


def _validate_common_siggen_test(
    test: Dict[str, Any],
    path: str,
    deterministic: bool,
    parameter_set: str,
    key_format: str = "expanded",
) -> None:
    require_int(require_field(test, "tcId", path), child_path(path, "tcId"))
    if key_format == "seed":
        require_hex_string(
            require_field(test, "seed", path),
            child_path(path, "seed"),
            allow_empty=False,
            exact_bytes=SEED_BYTES,
        )
    else:
        require_hex_string(
            require_field(test, "sk", path),
            child_path(path, "sk"),
            allow_empty=False,
            exact_bytes=SECRET_KEY_BYTES[parameter_set],
        )
    if deterministic:
        require_absent(test, "rnd", path, "deterministic is true")
    else:
        require_hex_string(
            require_field(test, "rnd", path),
            child_path(path, "rnd"),
            allow_empty=False,
            exact_bytes=RND_BYTES,
        )


def _validate_internal_message_or_mu(test: Dict[str, Any], path: str, external_mu: bool) -> None:
    if external_mu:
        require_hex_string(
            require_field(test, "mu", path),
            child_path(path, "mu"),
            allow_empty=False,
            exact_bytes=MU_BYTES,
        )
        require_absent(test, "message", path, "externalMu is true")
    else:
        require_hex_string(require_field(test, "message", path), child_path(path, "message"), allow_empty=False)
        require_absent(test, "mu", path, "externalMu is false")
    require_absent(test, "context", path, "signatureInterface is internal")
    require_absent(test, "hashAlg", path, "signatureInterface is internal")


def _validate_external_message(test: Dict[str, Any], path: str, pre_hash: str) -> None:
    require_hex_string(require_field(test, "message", path), child_path(path, "message"), allow_empty=False)
    require_hex_string(
        require_field(test, "context", path),
        child_path(path, "context"),
        allow_empty=True,
        max_bytes=CONTEXT_MAX_BYTES,
    )
    require_absent(test, "mu", path, "signatureInterface is external")
    if pre_hash == "preHash":
        require_enum(require_field(test, "hashAlg", path), HASH_ALGORITHMS, child_path(path, "hashAlg"))
    else:
        require_absent(test, "hashAlg", path, "preHash is pure")
