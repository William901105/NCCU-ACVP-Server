from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mldsa.response_schema import validate_response
from app.algorithms.mldsa.vector_schema import validate_vector_set


SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-data"


def test_vector_set_accepts_keygen_sample() -> None:
    payload = json.loads((SAMPLE_ROOT / "ML-DSA-keyGen-FIPS204" / "prompt.json").read_text())

    normalized = validate_vector_set(payload)

    assert normalized["mode"] == "keyGen"


def test_response_accepts_sigver_sample() -> None:
    payload = json.loads((SAMPLE_ROOT / "ML-DSA-sigVer-FIPS204" / "response.pass.json").read_text())

    normalized = validate_response(payload, expected_mode="sigVer")

    assert normalized["mode"] == "sigVer"


def test_vector_set_rejects_duplicate_tc_id() -> None:
    payload = {
        "vsId": 1,
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": "ML-DSA-44",
                "tests": [
                    {"tcId": 1, "seed": "00" * 32},
                    {"tcId": 1, "seed": "02" * 32},
                ],
            }
        ],
    }

    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_vector_set(payload)

    assert exc_info.value.code == "duplicate_tcId"


def test_response_rejects_missing_keygen_pk() -> None:
    payload = {
        "vsId": 1,
        "mode": "keyGen",
        "testGroups": [{"tgId": 1, "tests": [{"tcId": 1, "sk": "00"}]}],
    }

    with pytest.raises(AcvpSchemaError) as exc_info:
        validate_response(payload)

    assert exc_info.value.code == "missing_required_field"
    assert exc_info.value.path == "$.testGroups[0].tests[0].pk"
