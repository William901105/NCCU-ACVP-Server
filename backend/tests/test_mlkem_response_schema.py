from __future__ import annotations

import pytest

from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mlkem.response_schema import validate_response


def test_stage4_expected_results_are_positive_golden_fixtures(load_mlkem_fixture) -> None:
    for mode in ("keyGen", "encapDecap"):
        response = load_mlkem_fixture(mode, "expectedResults")
        assert validate_response(response)["mode"] == mode


@pytest.mark.parametrize(
    "test",
    [
        {"tcId": 1, "c": "00" * 768, "k": "11" * 32},
        {"tcId": 1, "k": "11" * 32},
        {"tcId": 1, "testPassed": False},
    ],
)
def test_encap_decap_response_shapes_can_be_inferred(test: dict) -> None:
    payload = {"vsId": 1, "testGroups": [{"tgId": 1, "tests": [test]}]}
    assert validate_response(payload)["vsId"] == 1


def test_response_accepts_nist_array_container(load_mlkem_fixture) -> None:
    response = load_mlkem_fixture("keyGen", "expectedResults")
    response.pop("acvVersion", None)
    assert validate_response([{"acvVersion": "1.0"}, response])["acvVersion"] == "1.0"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda p: p["testGroups"][0]["tests"][0].update(ek="00" * 1184), "invalid_length"),
        (lambda p: p["testGroups"][0]["tests"][0].update(pk=p["testGroups"][0]["tests"][0].pop("ek")), "unknown_field"),
        (lambda p: p["testGroups"][1].update(tgId=p["testGroups"][0]["tgId"]), "duplicate_tgId"),
        (lambda p: p["testGroups"][1]["tests"][0].update(tcId=p["testGroups"][0]["tests"][0]["tcId"]), "duplicate_tcId"),
    ],
)
def test_keygen_response_rejects_schema_violations(
    load_mlkem_fixture,
    mutation,
    code: str,
) -> None:
    response = load_mlkem_fixture("keyGen", "expectedResults")
    mutation(response)
    _assert_error(response, code)


@pytest.mark.parametrize(
    ("test", "code"),
    [
        ({"tcId": 1, "c": "00" * 767, "k": "00" * 32}, "invalid_length"),
        ({"tcId": 1, "c": "00" * 768, "k": "00" * 31}, "invalid_length"),
        ({"tcId": 1, "testPassed": "true"}, "invalid_type"),
        ({"tcId": 1, "signature": "00"}, "unknown_field"),
    ],
)
def test_encap_decap_response_rejects_invalid_case_shapes(test: dict, code: str) -> None:
    payload = {
        "vsId": 1,
        "mode": "encapDecap",
        "testGroups": [{"tgId": 1, "tests": [test]}],
    }
    _assert_error(payload, code)


def test_response_rejects_mixed_shapes_within_one_group() -> None:
    payload = {
        "vsId": 1,
        "mode": "encapDecap",
        "testGroups": [
            {
                "tgId": 1,
                "tests": [
                    {"tcId": 1, "k": "00" * 32},
                    {"tcId": 2, "testPassed": True},
                ],
            }
        ],
    }
    _assert_error(payload, "mixed_response_shapes")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("algorithm", "ML-DSA", "unsupported_algorithm"),
        ("revision", "FIPS204", "unsupported_revision"),
        ("mode", "sigGen", "invalid_mode"),
    ],
)
def test_response_rejects_wrong_identity(field: str, value: str, code: str) -> None:
    payload = {
        "vsId": 1,
        "mode": "keyGen",
        "testGroups": [
            {"tgId": 1, "tests": [{"tcId": 1, "ek": "00" * 800, "dk": "00" * 1632}]}
        ],
    }
    payload[field] = value
    _assert_error(payload, code)


def test_response_rejects_top_level_mode_that_disagrees_with_expected_mode() -> None:
    payload = {
        "vsId": 1,
        "mode": "keyGen",
        "testGroups": [{"tgId": 1, "tests": [{"tcId": 1, "k": "00" * 32}]}],
    }
    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_response(payload, expected_mode="encapDecap")
    assert exc_info.value.code == "invalid_mode"
    assert exc_info.value.path == "$.mode"


def _assert_error(payload: dict, code: str) -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_response(payload)
    assert exc_info.value.code == code
    assert exc_info.value.path
