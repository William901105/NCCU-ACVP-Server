from __future__ import annotations

import pytest

from app.acvp_core.schema_error import AcvpSchemaError
from app.algorithms.mldsa.normalize import normalize_acvp_container


def test_normalize_accepts_nist_array_container() -> None:
    payload = [
        {"acvVersion": "1.0"},
        {
            "vsId": 1,
            "algorithm": "ML-DSA",
            "mode": "keyGen",
            "revision": "FIPS204",
            "testGroups": [],
        },
    ]

    normalized = normalize_acvp_container(payload)

    assert normalized["acvVersion"] == "1.0"
    assert normalized["algorithm"] == "ML-DSA"


def test_normalize_accepts_legacy_object_container() -> None:
    normalized = normalize_acvp_container({"vsId": 1})

    assert normalized == {"vsId": 1, "acvVersion": None}


def test_normalize_rejects_invalid_container() -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        normalize_acvp_container("not-json-object")

    assert exc_info.value.code == "invalid_container"
