from __future__ import annotations

from copy import deepcopy

from app.algorithms.mlkem import MlkemAlgorithmModule


def test_stage4_registrations_map_with_exact_fixture_parity(load_mlkem_fixture) -> None:
    module = MlkemAlgorithmModule()
    for mode in ("keyGen", "encapDecap"):
        expected = load_mlkem_fixture(mode, "registration")
        registration = {
            key: deepcopy(value)
            for key, value in expected.items()
            if key not in {"vsId", "isSample"}
        }
        assert module.to_nist_registration(
            registration,
            vs_id=42,
            is_sample=True,
        ) == expected


def test_mapper_honors_custom_identity_fields_and_preserves_prerequisites() -> None:
    registration = {
        "algorithm": "ML-KEM",
        "mode": "keyGen",
        "revision": "FIPS203",
        "parameterSets": ["ML-KEM-768"],
        "prereqVals": [{"algorithm": "SHA", "valValue": "A1234"}],
    }
    mapped = MlkemAlgorithmModule().to_nist_registration(
        registration,
        vs_id=987,
        is_sample=False,
    )

    assert mapped == {
        "vsId": 987,
        "algorithm": "ML-KEM",
        "mode": "keyGen",
        "revision": "FIPS203",
        "isSample": False,
        "parameterSets": ["ML-KEM-768"],
        "prereqVals": [{"algorithm": "SHA", "valValue": "A1234"}],
    }
    registration["prereqVals"][0]["valValue"] = "changed"
    assert mapped["prereqVals"][0]["valValue"] == "A1234"


def test_mapper_does_not_emit_server_policy_or_generation_controls() -> None:
    mapped = MlkemAlgorithmModule().to_nist_registration(
        {
            "algorithm": "ML-KEM",
            "mode": "encapDecap",
            "revision": "FIPS203",
            "parameterSets": ["ML-KEM-512"],
            "functions": ["decapsulation"],
        },
        vs_id=1,
        is_sample=True,
    )
    forbidden = {
        "campaignSeed",
        "testsPerGroup",
        "generationProfile",
        "workflowPolicy",
        "executionBackend",
    }
    assert forbidden.isdisjoint(mapped)
