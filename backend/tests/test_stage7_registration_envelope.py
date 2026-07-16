from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.main import app
from helpers.mlkem_e2e import body, error, install_deterministic_genval, session_request


def envelope(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [{"acvVersion": "1.0"}, payload]


@pytest.mark.parametrize("modes", [("keyGen",), ("encapDecap",), ("keyGen", "encapDecap")])
def test_canonical_mlkem_registration_envelopes(
    monkeypatch: Any,
    tmp_path: Any,
    modes: tuple[str, ...],
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    request = session_request(*modes, auto_generate=False)
    with TestClient(app) as client:
        response = client.post("/acvp/v1/testSessions", json=envelope(request))

    assert response.status_code == 200
    created = body(response)
    assert created["status"] == "capabilitiesAccepted"
    assert created["vsIds"] == []
    assert response.headers.get("Deprecation") is None
    assert {item["mode"] for item in created["negotiatedCapabilities"]["negotiated"]} == set(
        modes
    )


def test_bare_registration_is_deprecated_but_equivalent(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    request = session_request("keyGen", auto_generate=False)
    with TestClient(app) as client:
        canonical_response = client.post("/acvp/v1/testSessions", json=envelope(request))
        legacy_response = client.post("/acvp/v1/testSessions", json=request)

    assert canonical_response.status_code == legacy_response.status_code == 200
    assert legacy_response.headers["Deprecation"] == "true"
    assert "canonical ACVP request envelope" in legacy_response.headers["Warning"]
    canonical = body(canonical_response)
    legacy = body(legacy_response)
    for key in (
        "status",
        "negotiatedCapabilities",
        "negotiationWarnings",
        "unsupported",
        "campaignSeed",
        "testsPerGroup",
        "isSample",
        "vsIds",
    ):
        assert canonical[key] == legacy[key]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("not-an-envelope", "INVALID_ACVP_ENVELOPE"),
        ([], "INVALID_ACVP_ENVELOPE"),
        ([{"acvVersion": "1.0"}], "INVALID_ACVP_ENVELOPE"),
        ([{}, {"algorithms": []}], "INVALID_ACVP_ENVELOPE"),
        (
            [{"acvVersion": "1.0", "extra": True}, {"algorithms": []}],
            "INVALID_ACVP_ENVELOPE",
        ),
        (
            [{"acvVersion": "2.0"}, {"algorithms": []}],
            "UNSUPPORTED_ACVP_VERSION",
        ),
        ([{"acvVersion": "1.0"}, []], "INVALID_ACVP_ENVELOPE"),
        (
            [{"acvVersion": "1.0"}, {"algorithms": []}, {}],
            "INVALID_ACVP_ENVELOPE",
        ),
    ],
)
def test_malformed_registration_envelopes_are_structured(
    payload: Any,
    code: str,
) -> None:
    with TestClient(app) as client:
        response = client.post("/acvp/v1/testSessions", json=payload)

    assert response.status_code == 400
    assert error(response)["code"] == code


def test_legacy_body_cannot_bypass_registration_schema() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/acvp/v1/testSessions",
            json={"algorithms": [{"algorithm": "ML-KEM", "mode": "unknown"}]},
        )

    assert response.status_code == 400
    assert error(response)["code"] != "INVALID_ACVP_ENVELOPE"
