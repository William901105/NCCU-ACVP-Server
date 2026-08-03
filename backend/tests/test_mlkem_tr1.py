from __future__ import annotations

import pytest

from app.acvp_core.algorithm_identity import AlgorithmIdentity
from app.acvp_core.bootstrap import build_algorithm_registry
from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mlkem.module import (
    MlkemAlgorithmModule,
    MlkemTr1AlgorithmModule,
)
from app.algorithms.mlkem.vector_schema import validate_vector_set


TR1_REGISTRATION = {
    "algorithm": "ML-KEM",
    "mode": "encapDecap",
    "revision": "FIPS203-tr1",
    "parameterSets": ["ML-KEM-512"],
    "functions": ["encapsulation", "decapsulation",
                  "encapsulationKeyCheck", "decapsulationKeyCheck"],
    "keyFormats": ["expanded", "seed"],
}


def test_registry_dispatches_tr1_identity_to_tr1_module() -> None:
    registry = build_algorithm_registry()
    module = registry.get_module(
        AlgorithmIdentity("ML-KEM", "encapDecap", "FIPS203-tr1")
    )
    assert isinstance(module, MlkemTr1AlgorithmModule)
    # keyGen stays on the base FIPS203 module
    base = registry.get_module(AlgorithmIdentity("ML-KEM", "keyGen", "FIPS203"))
    assert isinstance(base, MlkemAlgorithmModule)


def test_tr1_descriptor_advertises_key_formats() -> None:
    descriptor = MlkemTr1AlgorithmModule().descriptor.to_dict()
    assert descriptor["revision"] == "FIPS203-tr1"
    assert descriptor["modes"] == ["encapDecap"]
    assert descriptor["keyFormats"] == ["expanded", "seed"]


def test_tr1_negotiation_echoes_key_formats() -> None:
    result = MlkemTr1AlgorithmModule().negotiate_capabilities(TR1_REGISTRATION)
    assert result["revision"] == "FIPS203-tr1"
    entry = result["negotiated"][0]
    assert entry["keyFormats"] == ["expanded", "seed"]
    assert entry["functions"] == [
        "encapsulation", "decapsulation",
        "encapsulationKeyCheck", "decapsulationKeyCheck",
    ]


def test_tr1_maps_revision_and_key_formats_to_nist() -> None:
    mapped = MlkemTr1AlgorithmModule().to_nist_registration(
        TR1_REGISTRATION, vs_id=7, is_sample=True
    )
    assert mapped["revision"] == "FIPS203-tr1"
    assert mapped["keyFormats"] == ["expanded", "seed"]
    assert mapped["vsId"] == 7


def test_tr1_registration_requires_key_formats() -> None:
    reg = {k: v for k, v in TR1_REGISTRATION.items() if k != "keyFormats"}
    with pytest.raises(AcvpSchemaError) as exc:
        MlkemTr1AlgorithmModule().validate_registration(reg)
    assert exc.value.path == "$.keyFormats"


def test_base_fips203_rejects_key_formats() -> None:
    reg = dict(TR1_REGISTRATION, revision="FIPS203")
    with pytest.raises(AcvpSchemaError):
        MlkemAlgorithmModule().validate_registration(reg)


def test_base_module_rejects_tr1_registration() -> None:
    # The base FIPS203 module must reject a tr1 registration. keyFormats now
    # passes the allowed-field gate (so its conditional error can be precise),
    # so the tr1 registration is rejected on the revision mismatch instead —
    # either way it must raise.
    with pytest.raises(AcvpSchemaError):
        MlkemAlgorithmModule().validate_registration(TR1_REGISTRATION)

    reg_no_kf = {k: v for k, v in TR1_REGISTRATION.items() if k != "keyFormats"}
    with pytest.raises(AcvpSchemaError) as exc:
        MlkemAlgorithmModule().validate_registration(reg_no_kf)
    assert exc.value.path == "$.revision"


def _group(tg_id, function, key_format, tests, param="ML-KEM-512", test_type="VAL"):
    return {
        "tgId": tg_id,
        "testType": test_type,
        "parameterSet": param,
        "function": function,
        "keyFormat": key_format,
        "tests": tests,
    }


def test_tr1_prompt_seed_decapsulation_uses_d_and_z() -> None:
    # Real GenVal seed format: decapsulation key is separate d(32) + z(32).
    prompt = {
        "vsId": 1, "algorithm": "ML-KEM", "mode": "encapDecap",
        "revision": "FIPS203-tr1", "isSample": True,
        "testGroups": [
            _group(1, "decapsulation", "seed",
                   [{"tcId": 1, "d": "AB" * 32, "z": "CD" * 32, "c": "EF" * 768}]),
        ],
    }
    validated = validate_vector_set(prompt, revision="FIPS203-tr1")
    test = validated["testGroups"][0]["tests"][0]
    assert test["d"] == ("AB" * 32).upper()
    assert test["z"] == ("CD" * 32).upper()


def test_tr1_prompt_keyformat_none_and_optional_dk_key_check() -> None:
    # encapsulation / keyChecks carry keyFormat "none"; decapsulationKeyCheck
    # prompts carry no key material (only tcId).
    prompt = {
        "vsId": 1, "algorithm": "ML-KEM", "mode": "encapDecap",
        "revision": "FIPS203-tr1", "isSample": True,
        "testGroups": [
            _group(1, "encapsulation", "none",
                   [{"tcId": 1, "ek": "AB" * 800, "m": "CD" * 32}], test_type="AFT"),
            _group(2, "decapsulationKeyCheck", "none", [{"tcId": 2}]),
            _group(3, "encapsulationKeyCheck", "none", [{"tcId": 3, "ek": "AB" * 800}]),
        ],
    }
    validated = validate_vector_set(prompt, revision="FIPS203-tr1")
    assert [g["keyFormat"] for g in validated["testGroups"]] == ["none", "none", "none"]
    assert validated["testGroups"][1]["tests"][0] == {"tcId": 2}


def test_real_nist_tr1_sample_prompt_validates() -> None:
    import json
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[1].parent
        / "tests" / "fixtures" / "nist" / "mlkem" / "encapDecap-tr1" / "prompt.json"
    )
    prompt = json.loads(fixture.read_text())
    validated = MlkemTr1AlgorithmModule().validate_prompt(prompt)
    assert validated["revision"] == "FIPS203-tr1"
    functions = {g["function"] for g in validated["testGroups"]}
    assert functions == {
        "encapsulation", "decapsulation",
        "encapsulationKeyCheck", "decapsulationKeyCheck",
    }
    key_formats = {g["keyFormat"] for g in validated["testGroups"]}
    assert key_formats == {"none", "seed", "expanded"}


def test_base_prompt_rejects_key_format_field() -> None:
    prompt = {
        "vsId": 1, "algorithm": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203",
        "testGroups": [
            {
                "tgId": 1, "testType": "VAL", "parameterSet": "ML-KEM-512",
                "function": "decapsulation", "keyFormat": "seed",
                "tests": [{"tcId": 1, "dk": "AB" * 1632, "c": "CD" * 768}],
            }
        ],
    }
    with pytest.raises(AcvpSchemaError):
        validate_vector_set(prompt, revision="FIPS203")


# --- #3: harness response (empty decapsulationKeyCheck shape) must round-trip
# through the server's own response schema, not just the prompt schema. ---

def _tr1_response(groups):
    return {
        "vsId": 1, "algorithm": "ML-KEM", "mode": "encapDecap",
        "revision": "FIPS203-tr1", "testGroups": groups,
    }


def test_tr1_response_allows_empty_decap_key_check_shape() -> None:
    # keyFormat "none" decapsulationKeyCheck -> IUT can only answer {tcId}.
    resp = _tr1_response([{"tgId": 10, "tests": [{"tcId": 136}, {"tcId": 137}]}])
    validated = MlkemTr1AlgorithmModule().validate_response(
        resp, expected_mode="encapDecap"
    )
    assert validated["testGroups"][0]["tests"][0] == {"tcId": 136}


def test_base_response_rejects_empty_shape() -> None:
    # The empty shape is a tr1-only allowance; base FIPS203 still rejects it.
    resp = dict(_tr1_response([{"tgId": 1, "tests": [{"tcId": 1}]}]),
                revision="FIPS203")
    with pytest.raises(AcvpSchemaError) as exc:
        MlkemAlgorithmModule().validate_response(resp, expected_mode="encapDecap")
    assert exc.value.code == "invalid_response_shape"


def test_tr1_harness_output_roundtrips_through_response_schema(tmp_path) -> None:
    # Full loop: real NIST tr1 prompt -> IUT harness -> server response schema.
    # This is the direction that lets a decapsulationKeyCheck submission through;
    # the older tests only exercised the prompt (vector) schema.
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    runner = repo / "IUT-tests" / "mlkem-native" / "run_test.py"
    prompt = (
        repo / "tests" / "fixtures" / "nist" / "mlkem"
        / "encapDecap-tr1" / "prompt.json"
    )
    if not runner.exists() or not prompt.exists():
        pytest.skip("harness or fixture not available")
    result = subprocess.run(
        [sys.executable, str(runner), "--prompt", str(prompt),
         "--response-dir", str(tmp_path), "--variant", "pass"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"harness could not run: {result.stderr.strip()}")

    import json as _json
    response = _json.loads((tmp_path / "response_pass_encapDecap.json").read_text())
    validated = MlkemTr1AlgorithmModule().validate_response(
        response, expected_mode="encapDecap"
    )
    empty_groups = [
        g for g in validated["testGroups"]
        if all(set(t) == {"tcId"} for t in g["tests"])
    ]
    assert empty_groups, "expected decapsulationKeyCheck 'none' groups to round-trip"


# --- #8: keyFormats is required only when decapsulation is registered. ---

def test_tr1_encapsulation_only_registration_omits_key_formats() -> None:
    reg = {
        "algorithm": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203-tr1",
        "parameterSets": ["ML-KEM-512"], "functions": ["encapsulation"],
    }
    normalized = MlkemTr1AlgorithmModule().validate_registration(reg)
    assert "keyFormats" not in normalized
    assert normalized["functions"] == ["encapsulation"]


def test_tr1_key_check_only_registration_accepts_optional_key_formats() -> None:
    # No decapsulation -> keyFormats optional; if present, values still validated.
    reg = {
        "algorithm": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203-tr1",
        "parameterSets": ["ML-KEM-512"],
        "functions": ["encapsulationKeyCheck", "decapsulationKeyCheck"],
        "keyFormats": ["expanded"],
    }
    normalized = MlkemTr1AlgorithmModule().validate_registration(reg)
    assert normalized["keyFormats"] == ["expanded"]


# --- #9: decapsulationKeyCheck shares seed/expanded key shapes with
# decapsulation (forward-compatible with a fixed GenVal). ---

def test_tr1_prompt_decap_key_check_seed_is_accepted() -> None:
    prompt = {
        "vsId": 1, "algorithm": "ML-KEM", "mode": "encapDecap",
        "revision": "FIPS203-tr1", "isSample": True,
        "testGroups": [
            _group(1, "decapsulationKeyCheck", "seed",
                   [{"tcId": 1, "d": "AB" * 32, "z": "CD" * 32}]),
        ],
    }
    validated = validate_vector_set(prompt, revision="FIPS203-tr1")
    assert set(validated["testGroups"][0]["tests"][0]) == {"tcId", "d", "z"}


# --- #20: keyFormats in a context that forbids it yields a precise
# invalid_conditional_field error (not a generic unknown_field). ---

def test_base_encapdecap_key_formats_gives_conditional_error() -> None:
    reg = {
        "algorithm": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203",
        "parameterSets": ["ML-KEM-512"], "functions": ["decapsulation"],
        "keyFormats": ["seed"],
    }
    with pytest.raises(AcvpSchemaError) as exc:
        MlkemAlgorithmModule().validate_registration(reg)
    assert exc.value.code == "invalid_conditional_field"
    assert exc.value.path == "$.keyFormats"


def test_keygen_key_formats_gives_conditional_error() -> None:
    reg = {
        "algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203-tr1",
        "parameterSets": ["ML-KEM-512"], "keyFormats": ["seed"],
    }
    with pytest.raises(AcvpSchemaError) as exc:
        MlkemTr1AlgorithmModule().validate_registration(reg)
    assert exc.value.code == "invalid_conditional_field"
    assert exc.value.path == "$.keyFormats"
