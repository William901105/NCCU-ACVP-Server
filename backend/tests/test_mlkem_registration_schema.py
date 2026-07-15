from __future__ import annotations

from copy import deepcopy

import pytest

from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mlkem.registration_schema import validate_registration


def _registration(mode: str = "keyGen") -> dict:
    payload = {
        "algorithm": "ML-KEM",
        "mode": mode,
        "revision": "FIPS203",
        "parameterSets": ["ML-KEM-512"],
    }
    if mode == "encapDecap":
        payload["functions"] = ["encapsulation"]
    return payload


def test_registration_accepts_all_capabilities_and_prerequisites() -> None:
    keygen = _registration()
    keygen["parameterSets"] = ["ML-KEM-1024", "ML-KEM-768", "ML-KEM-512"]
    keygen["prereqVals"] = [{"algorithm": "SHA", "valValue": "same"}]
    encap = _registration("encapDecap")
    encap["functions"] = [
        "decapsulationKeyCheck",
        "encapsulationKeyCheck",
        "decapsulation",
        "encapsulation",
    ]

    assert validate_registration(keygen)["parameterSets"] == keygen["parameterSets"]
    assert validate_registration(encap)["functions"] == encap["functions"]


@pytest.mark.parametrize(
    ("mutation", "code", "path"),
    [
        (lambda p: p.update(algorithm="ML-DSA"), "unsupported_algorithm", "$.algorithm"),
        (lambda p: p.update(revision="FIPS204"), "unsupported_revision", "$.revision"),
        (lambda p: p.update(mode="unknown"), "invalid_mode", "$.mode"),
        (lambda p: p.update(parameterSets=[]), "invalid_value", "$.parameterSets"),
        (lambda p: p.update(parameterSets=["ML-KEM-999"]), "invalid_parameter_set", "$.parameterSets[0]"),
        (lambda p: p.update(parameterSets=["ML-KEM-512", "ML-KEM-512"]), "duplicate_value", "$.parameterSets[1]"),
        (lambda p: p.update(parameterSets="ML-KEM-512"), "invalid_type", "$.parameterSets"),
        (lambda p: p.update(extra=True), "unknown_field", "$.extra"),
        (lambda p: p.update(functions=["encapsulation"]), "unknown_field", "$.functions"),
    ],
)
def test_keygen_registration_rejects_invalid_inputs(mutation, code: str, path: str) -> None:
    payload = _registration()
    mutation(payload)
    _assert_error(payload, code, path)


@pytest.mark.parametrize(
    ("mutation", "code", "path"),
    [
        (lambda p: p.pop("functions"), "missing_required_field", "$.functions"),
        (lambda p: p.update(functions=[]), "invalid_value", "$.functions"),
        (lambda p: p.update(functions=["unknown"]), "invalid_function", "$.functions[0]"),
        (lambda p: p.update(functions=["encapsulation", "encapsulation"]), "duplicate_value", "$.functions[1]"),
        (lambda p: p.update(functions=True), "invalid_type", "$.functions"),
    ],
)
def test_encap_decap_registration_rejects_invalid_functions(mutation, code: str, path: str) -> None:
    payload = _registration("encapDecap")
    mutation(payload)
    _assert_error(payload, code, path)


@pytest.mark.parametrize(
    "prereqs",
    [
        "SHA",
        ["SHA"],
        [{}],
        [{"algorithm": "", "valValue": "same"}],
        [{"algorithm": "SHA", "valValue": ""}],
        [{"algorithm": "SHA", "valValue": "same", "extra": 1}],
    ],
)
def test_registration_rejects_malformed_prerequisites(prereqs) -> None:
    payload = deepcopy(_registration())
    payload["prereqVals"] = prereqs
    with pytest.raises(AcvpSchemaError):
        validate_registration(payload)


def _assert_error(payload: dict, code: str, path: str) -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_registration(payload)
    assert exc_info.value.code == code
    assert exc_info.value.path == path
