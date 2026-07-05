from __future__ import annotations

from app.acvp_mldsa.nist_registration_mapper import (
    map_mldsa_registration_container_to_nist,
    map_mldsa_registration_to_nist,
)
from app.acvp_mldsa.nist_validation_mapper import normalize_nist_validation


def test_keygen_registration_maps_to_nist_shape() -> None:
    mapped = map_mldsa_registration_to_nist(
        {
            "algorithm": "ML-DSA",
            "mode": "keyGen",
            "revision": "FIPS204",
            "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
            "parameterSets": ["ML-DSA-44"],
        },
        vs_id=7,
    )

    assert mapped == {
        "vsId": 7,
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "isSample": True,
        "parameterSets": ["ML-DSA-44"],
    }


def test_siggen_registration_maps_to_nist_shape() -> None:
    mapped = map_mldsa_registration_to_nist(_sig_registration("sigGen"), vs_id=8, is_sample=False)

    assert mapped["vsId"] == 8
    assert mapped["mode"] == "sigGen"
    assert mapped["isSample"] is False
    assert mapped["deterministic"] == [True, False]
    assert mapped["externalMu"] == [False, True]
    assert mapped["signatureInterfaces"] == ["internal", "external"]
    assert mapped["preHash"] == ["pure", "preHash"]
    assert mapped["capabilities"][0]["parameterSets"] == ["ML-DSA-44"]


def test_sigver_registration_maps_to_nist_shape() -> None:
    mapped = map_mldsa_registration_to_nist(_sig_registration("sigVer"), vs_id=9)

    assert mapped["vsId"] == 9
    assert mapped["mode"] == "sigVer"
    assert "deterministic" not in mapped
    assert mapped["externalMu"] == [False, True]
    assert mapped["signatureInterfaces"] == ["internal", "external"]


def test_container_mapping_assigns_vs_ids() -> None:
    mapped = map_mldsa_registration_container_to_nist(
        {
            "algorithms": [
                {
                    "algorithm": "ML-DSA",
                    "mode": "keyGen",
                    "revision": "FIPS204",
                    "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
                    "parameterSets": ["ML-DSA-44"],
                },
                _sig_registration("sigVer"),
            ]
        },
        starting_vs_id=3,
    )

    assert [item["vsId"] for item in mapped] == [3, 4]
    assert [item["mode"] for item in mapped] == ["keyGen", "sigVer"]


def test_nist_validation_maps_to_existing_summary_shape() -> None:
    normalized = normalize_nist_validation(
        {
            "vsId": 1,
            "disposition": "failed",
            "tests": [
                {"tcId": 1, "result": "passed"},
                {"tcId": 2, "result": "failed", "reason": "signature mismatch"},
            ],
        },
        prompt={"vsId": 1, "algorithm": "ML-DSA", "mode": "sigVer", "revision": "FIPS204", "testGroups": []},
    )

    assert normalized["metadata"]["provider"] == "nist-genval"
    assert normalized["summary"] == {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "missing": 0,
        "malformed": 0,
        "extra": 0,
    }
    assert normalized["failures"][0]["tcId"] == 2
    assert normalized["nistValidation"]["disposition"] == "failed"


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
