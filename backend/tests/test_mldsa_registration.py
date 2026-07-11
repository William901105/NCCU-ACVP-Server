from __future__ import annotations

import pytest

from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mldsa.registration_schema import validate_registration


def test_valid_keygen_registration() -> None:
    payload = {
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "parameterSets": ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"],
    }

    assert validate_registration(payload)["mode"] == "keyGen"


def test_valid_siggen_registration() -> None:
    payload = {
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204",
        "deterministic": [True, False],
        "signatureInterfaces": ["internal", "external"],
        "preHash": ["pure", "preHash"],
        "externalMu": [True, False],
        "capabilities": [
            {
                "parameterSets": ["ML-DSA-44"],
                "messageLength": [{"min": 8, "max": 1024, "increment": 8}],
                "contextLength": [{"min": 0, "max": 128, "increment": 8}],
                "hashAlgs": ["SHA2-256", "SHA3-256"],
            }
        ],
    }

    assert validate_registration(payload)["mode"] == "sigGen"


def test_registration_rejects_bad_parameter_set() -> None:
    payload = {
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "parameterSets": ["ML-DSA-99"],
    }

    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_registration(payload)

    assert exc_info.value.code == "invalid_parameter_set"
    assert exc_info.value.path == "$.parameterSets[0]"
