from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import HTTPException

from app.crypto_oracle.mldsa_oracle import keygen_internal
from app.main import (
    DEMO_SESSION_STORE,
    clear_demo_data,
    create_demo_acvp_session,
    delete_demo_acvp_session,
    get_demo_acvp_session,
    get_demo_acvp_session_report,
    get_demo_acvp_session_validation,
    get_demo_acvp_session_vector_set,
    list_demo_acvp_sessions,
    submit_demo_acvp_session_response,
)
from app.models import DemoAcvpResponseSubmitRequest, DemoAcvpSessionCreateRequest
from app.storage.sqlite_store import get_db_path


SEED_32_BYTES = "000102030405060708090A0B0C0D0E0F101112131415161718191A1B1C1D1E1F"
MESSAGE_HEX = "00010203040506070809"


@pytest.fixture(autouse=True)
def clear_demo_sessions() -> None:
    DEMO_SESSION_STORE.clear()


def test_create_keygen_session_and_get_vector_set() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(
            prompt=_keygen_prompt(),
            label="keyGen demo",
        )
    )
    detail = get_demo_acvp_session(session["sessionId"])
    vector_set = get_demo_acvp_session_vector_set(session["sessionId"])

    assert session["status"] == "vectorReady"
    assert session["demoOnly"] is True
    assert session["notProductionAcvp"] is True
    assert detail["expectedResults"]["mode"] == "keyGen"
    assert vector_set["prompt"]["mode"] == "keyGen"


def test_create_siggen_session_expected_results_shape() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_siggen_prompt(_keypair()["sk"]))
    )
    detail = get_demo_acvp_session(session["sessionId"])
    test = detail["expectedResults"]["testGroups"][0]["tests"][0]

    assert detail["mode"] == "sigGen"
    assert sorted(test) == ["signature", "tcId"]


def test_submit_matching_response_validates() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_siggen_prompt(_keypair()["sk"]))
    )
    detail = get_demo_acvp_session(session["sessionId"])
    result = submit_demo_acvp_session_response(
        session["sessionId"],
        DemoAcvpResponseSubmitRequest(response=detail["expectedResults"]),
    )

    assert result["status"] == "validated"
    assert result["validationResult"]["summary"]["passed"] == 1
    assert result["demoOnly"] is True
    assert result["notProductionAcvp"] is True


def test_submit_wrong_response_marks_session_failed() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_siggen_prompt(_keypair()["sk"]))
    )
    detail = get_demo_acvp_session(session["sessionId"])
    response = copy.deepcopy(detail["expectedResults"])
    response["testGroups"][0]["tests"][0]["signature"] = _flip_first_hex_char(
        response["testGroups"][0]["tests"][0]["signature"]
    )

    result = submit_demo_acvp_session_response(
        session["sessionId"],
        DemoAcvpResponseSubmitRequest(response=response),
    )

    assert result["status"] == "failed"
    assert result["validationResult"]["summary"]["failed"] == 1


def test_get_report_after_submit_response() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_keygen_prompt())
    )
    detail = get_demo_acvp_session(session["sessionId"])
    submit_demo_acvp_session_response(
        session["sessionId"],
        DemoAcvpResponseSubmitRequest(response=detail["expectedResults"]),
    )

    report = get_demo_acvp_session_report(session["sessionId"])

    assert "markdown" in report
    assert report["failedCount"] == 0
    assert report["sessionId"] == session["sessionId"]
    assert report["demoOnly"] is True


def test_list_sessions_returns_summaries_without_vectors() -> None:
    first = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_keygen_prompt(), label="first")
    )
    second = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_siggen_prompt(_keypair()["sk"]), label="second")
    )

    body = list_demo_acvp_sessions()
    sessions = body["sessions"]

    assert body["demoOnly"] is True
    assert {item["sessionId"] for item in sessions} == {
        first["sessionId"],
        second["sessionId"],
    }
    assert all("prompt" not in item for item in sessions)
    assert all("expectedResults" not in item for item in sessions)


def test_missing_session_returns_404() -> None:
    with pytest.raises(HTTPException) as get_exc:
        get_demo_acvp_session("missing")
    with pytest.raises(HTTPException) as post_exc:
        submit_demo_acvp_session_response(
            "missing",
            DemoAcvpResponseSubmitRequest(response=_keygen_prompt()),
        )
    with pytest.raises(HTTPException) as delete_exc:
        delete_demo_acvp_session("missing")

    assert get_exc.value.status_code == 404
    assert post_exc.value.status_code == 404
    assert delete_exc.value.status_code == 404


def test_validation_and_report_before_response_return_409() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_keygen_prompt())
    )

    with pytest.raises(HTTPException) as validation_exc:
        get_demo_acvp_session_validation(session["sessionId"])
    with pytest.raises(HTTPException) as report_exc:
        get_demo_acvp_session_report(session["sessionId"])

    assert validation_exc.value.status_code == 409
    assert report_exc.value.status_code == 409


def test_delete_session_removes_it() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_keygen_prompt())
    )

    deleted = delete_demo_acvp_session(session["sessionId"])

    assert deleted["deleted"] is True
    with pytest.raises(HTTPException) as exc_info:
        get_demo_acvp_session(session["sessionId"])
    assert exc_info.value.status_code == 404


def test_clear_demo_data_requires_confirmation_and_resets_store() -> None:
    session = create_demo_acvp_session(
        DemoAcvpSessionCreateRequest(prompt=_keygen_prompt())
    )
    artifact_file = get_db_path().parent / "acvp-sessions" / "session-1" / "prompt.json"
    artifact_file.parent.mkdir(parents=True)
    artifact_file.write_text("{}", encoding="utf-8")

    with pytest.raises(HTTPException) as confirm_exc:
        clear_demo_data()
    cleaned = clear_demo_data(confirm=True)

    assert confirm_exc.value.status_code == 400
    assert cleaned["deleted"] is True
    assert not artifact_file.exists()
    assert str(Path(artifact_file.parents[1])) in cleaned["deletedFiles"]
    with pytest.raises(HTTPException) as get_exc:
        get_demo_acvp_session(session["sessionId"])
    assert get_exc.value.status_code == 404


def _keypair() -> Dict[str, str]:
    return keygen_internal("ML-DSA-44", SEED_32_BYTES)


def _keygen_prompt() -> Dict[str, Any]:
    return {
        "vsId": 9001,
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": "ML-DSA-44",
                "tests": [{"tcId": 1, "seed": SEED_32_BYTES}],
            }
        ],
    }


def _siggen_prompt(sk: str) -> Dict[str, Any]:
    return {
        "vsId": 9002,
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204",
        "testGroups": [
            {
                "tgId": 1,
                "testType": "AFT",
                "parameterSet": "ML-DSA-44",
                "signatureInterface": "internal",
                "externalMu": False,
                "deterministic": True,
                "tests": [{"tcId": 1, "sk": sk, "message": MESSAGE_HEX}],
            }
        ],
    }


def _flip_first_hex_char(value: str) -> str:
    first = "0" if value[0] != "0" else "1"
    return first + value[1:]
