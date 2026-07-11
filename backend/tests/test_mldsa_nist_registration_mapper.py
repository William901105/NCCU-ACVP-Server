from __future__ import annotations

from app.algorithms.mldsa import MldsaAlgorithmModule


MODULE = MldsaAlgorithmModule()


def test_keygen_registration_maps_to_nist_shape_through_module() -> None:
    mapped = MODULE.to_nist_registration(_keygen_registration(), vs_id=7, is_sample=True)

    assert mapped == {
        "vsId": 7,
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "isSample": True,
        "parameterSets": ["ML-DSA-44"],
    }


def test_signature_registrations_map_to_nist_shape_through_module() -> None:
    siggen = MODULE.to_nist_registration(_sig_registration("sigGen"), vs_id=8, is_sample=False)
    sigver = MODULE.to_nist_registration(_sig_registration("sigVer"), vs_id=9, is_sample=True)

    assert siggen["deterministic"] == [True, False]
    assert siggen["externalMu"] == [False, True]
    assert siggen["preHash"] == ["pure", "preHash"]
    assert siggen["isSample"] is False
    assert "deterministic" not in sigver
    assert sigver["mode"] == "sigVer"


def test_nist_validation_normalizes_through_module() -> None:
    normalized = MODULE.normalize_nist_validation(
        {
            "vsId": 1,
            "disposition": "failed",
            "tests": [
                {"tcId": 1, "result": "passed"},
                {"tcId": 2, "result": "failed", "reason": "signature mismatch"},
            ],
        },
        prompt={
            "vsId": 1,
            "algorithm": "ML-DSA",
            "mode": "sigVer",
            "revision": "FIPS204",
            "testGroups": [],
        },
    )

    assert normalized["metadata"]["provider"] == "nist-genval"
    assert normalized["summary"]["passed"] == 1
    assert normalized["summary"]["failed"] == 1
    assert normalized["failures"][0]["tcId"] == 2


def _keygen_registration() -> dict:
    return {
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
        "parameterSets": ["ML-DSA-44"],
    }


def _sig_registration(mode: str) -> dict:
    registration = {
        "algorithm": "ML-DSA",
        "mode": mode,
        "revision": "FIPS204",
        "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
        "signatureInterfaces": ["internal", "external"],
        "externalMu": [False, True],
        "preHash": ["pure", "preHash"],
        "capabilities": [
            {
                "parameterSets": ["ML-DSA-44"],
                "messageLength": [{"min": 8, "max": 128, "increment": 8}],
                "contextLength": [{"min": 0, "max": 64, "increment": 8}],
                "hashAlgs": ["SHA2-256"],
            }
        ],
    }
    if mode == "sigGen":
        registration["deterministic"] = [True, False]
    return registration
