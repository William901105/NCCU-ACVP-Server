from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from app.algorithms.mldsa.constants import (
    MU_BYTES,
    PUBLIC_KEY_BYTES,
    RND_BYTES,
    SECRET_KEY_BYTES,
    SEED_BYTES,
    SIGNATURE_BYTES,
)
from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mldsa.validators import validate_mldsa_response, validate_mldsa_vector_set


PARAMETER_SET = "ML-DSA-44"


def test_keygen_seed_exact_32_bytes_schema_validation() -> None:
    validate_mldsa_vector_set(_keygen_prompt(_hex(SEED_BYTES)))

    cases = (
        (_hex(SEED_BYTES - 1), "$.testGroups[0].tests[0].seed"),
        (_hex(SEED_BYTES + 1), "$.testGroups[0].tests[0].seed"),
        ("0" * ((SEED_BYTES * 2) - 1), "$.testGroups[0].tests[0].seed"),
        ("GG" * SEED_BYTES, "$.testGroups[0].tests[0].seed"),
    )
    for seed, path in cases:
        with pytest.raises(AcvpSchemaError) as exc_info:
            validate_mldsa_vector_set(_keygen_prompt(seed))
        assert exc_info.value.path == path


def test_keygen_response_exact_lengths_and_unknown_fields() -> None:
    response = _keygen_response()
    validate_mldsa_response(response, expected_mode="keyGen")

    pk_short = copy.deepcopy(response)
    pk_short["testGroups"][0]["tests"][0]["pk"] = _hex(PUBLIC_KEY_BYTES[PARAMETER_SET] - 1)
    _assert_schema_error(pk_short, "keyGen", "invalid_length", "$.testGroups[0].tests[0].pk")

    sk_short = copy.deepcopy(response)
    sk_short["testGroups"][0]["tests"][0]["sk"] = _hex(SECRET_KEY_BYTES[PARAMETER_SET] - 1)
    _assert_schema_error(sk_short, "keyGen", "invalid_length", "$.testGroups[0].tests[0].sk")

    extra_test = copy.deepcopy(response)
    extra_test["testGroups"][0]["tests"][0]["foo"] = "bar"
    _assert_schema_error(extra_test, "keyGen", "unknown_field", "$.testGroups[0].tests[0].foo")

    extra_group = copy.deepcopy(response)
    extra_group["testGroups"][0]["parameterSet"] = PARAMETER_SET
    _assert_schema_error(extra_group, "keyGen", "unknown_field", "$.testGroups[0].parameterSet")


def test_siggen_prompt_exact_lengths_and_conditionals() -> None:
    validate_mldsa_vector_set(_siggen_prompt())

    sk_short = _siggen_prompt()
    sk_short["testGroups"][0]["tests"][0]["sk"] = _hex(SECRET_KEY_BYTES[PARAMETER_SET] - 1)
    _assert_vector_error(sk_short, "invalid_hex", "$.testGroups[0].tests[0].sk")

    rnd_short = _siggen_prompt(deterministic=False)
    rnd_short["testGroups"][0]["tests"][0]["rnd"] = _hex(RND_BYTES - 1)
    _assert_vector_error(rnd_short, "invalid_hex", "$.testGroups[0].tests[0].rnd")

    mu_short = _siggen_prompt(external_mu=True)
    mu_short["testGroups"][0]["tests"][0]["mu"] = _hex(MU_BYTES - 1)
    _assert_vector_error(mu_short, "invalid_hex", "$.testGroups[0].tests[0].mu")

    context_too_long = _siggen_prompt_external()
    context_too_long["testGroups"][0]["tests"][0]["context"] = _hex(256)
    _assert_vector_error(context_too_long, "invalid_hex", "$.testGroups[0].tests[0].context")

    extra_test = _siggen_prompt()
    extra_test["testGroups"][0]["tests"][0]["pk"] = _hex(PUBLIC_KEY_BYTES[PARAMETER_SET])
    _assert_vector_error(extra_test, "unknown_field", "$.testGroups[0].tests[0].pk")


def test_siggen_response_exact_signature_length_and_unknown_fields() -> None:
    response = _siggen_response()
    validate_mldsa_response(response, expected_mode="sigGen")

    short = copy.deepcopy(response)
    short["testGroups"][0]["tests"][0]["signature"] = _hex(SIGNATURE_BYTES[PARAMETER_SET] - 1)
    _assert_schema_error(short, "sigGen", "invalid_length", "$.testGroups[0].tests[0].signature")

    long = copy.deepcopy(response)
    long["testGroups"][0]["tests"][0]["signature"] = _hex(SIGNATURE_BYTES[PARAMETER_SET] + 1)
    _assert_schema_error(long, "sigGen", "invalid_length", "$.testGroups[0].tests[0].signature")

    extra_test = copy.deepcopy(response)
    extra_test["testGroups"][0]["tests"][0]["message"] = "00"
    _assert_schema_error(extra_test, "sigGen", "unknown_field", "$.testGroups[0].tests[0].message")

    extra_group = copy.deepcopy(response)
    extra_group["testGroups"][0]["parameterSet"] = PARAMETER_SET
    _assert_schema_error(extra_group, "sigGen", "unknown_field", "$.testGroups[0].parameterSet")


def test_sigver_prompt_and_response_strict_schema() -> None:
    prompt = _sigver_prompt()
    validate_mldsa_vector_set(prompt)

    wrong_pk = copy.deepcopy(prompt)
    wrong_pk["testGroups"][0]["tests"][0]["pk"] = _hex(PUBLIC_KEY_BYTES[PARAMETER_SET] - 1)
    _assert_vector_error(wrong_pk, "invalid_hex", "$.testGroups[0].tests[0].pk")

    wrong_signature = copy.deepcopy(prompt)
    wrong_signature["testGroups"][0]["tests"][0]["signature"] = _hex(SIGNATURE_BYTES[PARAMETER_SET] + 1)
    _assert_vector_error(wrong_signature, "invalid_hex", "$.testGroups[0].tests[0].signature")

    response = _sigver_response(True)
    validate_mldsa_response(response, expected_mode="sigVer")

    string_bool = _sigver_response("true")
    _assert_schema_error(string_bool, "sigVer", "invalid_type", "$.testGroups[0].tests[0].testPassed")

    extra_test = _sigver_response(False)
    extra_test["testGroups"][0]["tests"][0]["signature"] = _hex(SIGNATURE_BYTES[PARAMETER_SET])
    _assert_schema_error(extra_test, "sigVer", "unknown_field", "$.testGroups[0].tests[0].signature")


def _keygen_prompt(seed: str) -> Dict[str, Any]:
    return {
        "vsId": 1,
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": PARAMETER_SET,
                "tests": [{"tcId": 1, "seed": seed}],
            }
        ],
    }


def _keygen_response() -> Dict[str, Any]:
    return {
        "vsId": 1,
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "tests": [
                    {
                        "tcId": 1,
                        "pk": _hex(PUBLIC_KEY_BYTES[PARAMETER_SET]),
                        "sk": _hex(SECRET_KEY_BYTES[PARAMETER_SET]),
                    }
                ],
            }
        ],
    }


def _siggen_prompt(
    *,
    deterministic: bool = True,
    external_mu: bool = False,
) -> Dict[str, Any]:
    test: Dict[str, Any] = {
        "tcId": 1,
        "sk": _hex(SECRET_KEY_BYTES[PARAMETER_SET]),
    }
    if external_mu:
        test["mu"] = _hex(MU_BYTES)
    else:
        test["message"] = "AA"
    if not deterministic:
        test["rnd"] = _hex(RND_BYTES)
    return {
        "vsId": 2,
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": PARAMETER_SET,
                "deterministic": deterministic,
                "signatureInterface": "internal",
                "externalMu": external_mu,
                "tests": [test],
            }
        ],
    }


def _siggen_prompt_external() -> Dict[str, Any]:
    return {
        "vsId": 3,
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": PARAMETER_SET,
                "deterministic": True,
                "signatureInterface": "external",
                "preHash": "preHash",
                "tests": [
                    {
                        "tcId": 1,
                        "sk": _hex(SECRET_KEY_BYTES[PARAMETER_SET]),
                        "message": "AA",
                        "context": "",
                        "hashAlg": "SHA2-256",
                    }
                ],
            }
        ],
    }


def _siggen_response() -> Dict[str, Any]:
    return {
        "vsId": 2,
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "tests": [
                    {
                        "tcId": 1,
                        "signature": _hex(SIGNATURE_BYTES[PARAMETER_SET]),
                    }
                ],
            }
        ],
    }


def _sigver_prompt() -> Dict[str, Any]:
    return {
        "vsId": 4,
        "algorithm": "ML-DSA",
        "mode": "sigVer",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": PARAMETER_SET,
                "signatureInterface": "internal",
                "externalMu": False,
                "tests": [
                    {
                        "tcId": 1,
                        "pk": _hex(PUBLIC_KEY_BYTES[PARAMETER_SET]),
                        "message": "AA",
                        "signature": _hex(SIGNATURE_BYTES[PARAMETER_SET]),
                    }
                ],
            }
        ],
    }


def _sigver_response(test_passed: Any) -> Dict[str, Any]:
    return {
        "vsId": 4,
        "algorithm": "ML-DSA",
        "mode": "sigVer",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "tests": [{"tcId": 1, "testPassed": test_passed}],
            }
        ],
    }


def _assert_vector_error(payload: Dict[str, Any], code: str, path: str) -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_mldsa_vector_set(payload)
    assert exc_info.value.code == code
    assert exc_info.value.path == path


def _assert_schema_error(payload: Dict[str, Any], mode: str, code: str, path: str) -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_mldsa_response(payload, expected_mode=mode)
    assert exc_info.value.code == code
    assert exc_info.value.path == path


def _hex(byte_len: int) -> str:
    return "A5" * byte_len
