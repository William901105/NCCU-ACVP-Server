from __future__ import annotations

import pytest

from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mlkem.vector_schema import validate_vector_set


def test_stage4_prompts_are_positive_golden_fixtures(load_mlkem_fixture) -> None:
    for mode in ("keyGen", "encapDecap"):
        prompt = load_mlkem_fixture(mode, "prompt")
        normalized = validate_vector_set(prompt)
        assert normalized["mode"] == mode


def test_vector_accepts_nist_array_container(load_mlkem_fixture) -> None:
    prompt = load_mlkem_fixture("keyGen", "prompt")
    prompt.pop("acvVersion", None)
    normalized = validate_vector_set([{"acvVersion": "1.0"}, prompt])
    assert normalized["acvVersion"] == "1.0"


@pytest.mark.parametrize(
    ("function", "field"),
    [
        ("encapsulationKeyCheck", "ek"),
        ("decapsulationKeyCheck", "dk"),
    ],
)
def test_key_checks_accept_intentionally_abnormal_encoded_key_lengths(
    load_mlkem_fixture,
    function: str,
    field: str,
) -> None:
    prompt = load_mlkem_fixture("encapDecap", "prompt")
    group = next(g for g in prompt["testGroups"] if g["function"] == function)
    group["tests"] = [{"tcId": 9000, field: "AA"}]
    prompt["testGroups"] = [group]
    assert validate_vector_set(prompt)["testGroups"][0]["tests"][0][field] == "AA"


@pytest.mark.parametrize(
    ("function", "field"),
    [
        ("encapsulationKeyCheck", "ek"),
        ("decapsulationKeyCheck", "dk"),
    ],
)
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda test, field: test.update({field: ""}), "invalid_hex"),
        (lambda test, field: test.update({field: "A"}), "invalid_hex"),
        (lambda test, field: test.update({field: "GG"}), "invalid_hex"),
        (lambda test, field: test.update(unexpected="AA"), "unknown_field"),
        (lambda test, field: test.pop(field), "missing_required_field"),
    ],
)
def test_key_checks_reject_malformed_inputs_and_field_shapes(
    load_mlkem_fixture,
    function: str,
    field: str,
    mutation,
    code: str,
) -> None:
    prompt = load_mlkem_fixture("encapDecap", "prompt")
    group = next(g for g in prompt["testGroups"] if g["function"] == function)
    group["tests"] = [{"tcId": 9000, field: "AA"}]
    prompt["testGroups"] = [group]
    mutation(group["tests"][0], field)

    _assert_error(prompt, code)


@pytest.mark.parametrize("function", ["encapsulationKeyCheck", "decapsulationKeyCheck"])
def test_key_checks_reject_wrong_test_type(load_mlkem_fixture, function: str) -> None:
    prompt = load_mlkem_fixture("encapDecap", "prompt")
    group = next(g for g in prompt["testGroups"] if g["function"] == function)
    group["testType"] = "AFT"
    prompt["testGroups"] = [group]

    _assert_error(prompt, "invalid_test_type")


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda p: p["testGroups"].__setitem__(1, {**p["testGroups"][1], "tgId": p["testGroups"][0]["tgId"]}), "duplicate_tgId"),
        (lambda p: p["testGroups"][1]["tests"][0].update(tcId=p["testGroups"][0]["tests"][0]["tcId"]), "duplicate_tcId"),
        (lambda p: p["testGroups"][0].update(testType="VAL"), "invalid_test_type"),
        (lambda p: p["testGroups"][0].update(parameterSet="ML-KEM-999"), "invalid_parameter_set"),
        (lambda p: p["testGroups"][0]["tests"][0].update(d="0"), "invalid_hex"),
        (lambda p: p["testGroups"][0]["tests"][0].update(z="GG" * 32), "invalid_hex"),
        (lambda p: p["testGroups"][0]["tests"][0].update(d="00" * 31), "invalid_length"),
        (lambda p: p["testGroups"][0]["tests"][0].pop("z"), "missing_required_field"),
        (lambda p: p["testGroups"][0]["tests"][0].update(seed="00" * 32), "unknown_field"),
    ],
)
def test_keygen_vector_rejects_schema_violations(
    load_mlkem_fixture,
    mutation,
    code: str,
) -> None:
    prompt = load_mlkem_fixture("keyGen", "prompt")
    mutation(prompt)
    _assert_error(prompt, code)


@pytest.mark.parametrize(
    ("select_function", "mutation", "code"),
    [
        ("encapsulation", lambda g: g.update(testType="VAL"), "invalid_test_type"),
        ("encapsulation", lambda g: g.update(function="unknown"), "invalid_function"),
        ("encapsulation", lambda g: g["tests"][0].update(m="00" * 31), "invalid_length"),
        ("encapsulation", lambda g: g["tests"][0].update(ek="00" * 799), "invalid_length"),
        ("encapsulation", lambda g: g["tests"][0].update(c="00"), "unknown_field"),
        ("decapsulation", lambda g: g["tests"][0].update(dk="00" * 1631), "invalid_length"),
        ("decapsulation", lambda g: g["tests"][0].update(c="00" * 767), "invalid_length"),
        ("decapsulation", lambda g: g["tests"][0].pop("c"), "missing_required_field"),
    ],
)
def test_encap_decap_vector_rejects_schema_violations(
    load_mlkem_fixture,
    select_function: str,
    mutation,
    code: str,
) -> None:
    prompt = load_mlkem_fixture("encapDecap", "prompt")
    group = next(
        g
        for g in prompt["testGroups"]
        if g["function"] == select_function and g["parameterSet"] == "ML-KEM-512"
    )
    prompt["testGroups"] = [group]
    mutation(group)
    _assert_error(prompt, code)


def _assert_error(payload: dict, code: str) -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_vector_set(payload)
    assert exc_info.value.code == code
    assert exc_info.value.path
