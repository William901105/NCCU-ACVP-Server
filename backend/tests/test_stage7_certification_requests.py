from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.sqlite_store import get_acvp_request
from helpers.mlkem_e2e import (
    body,
    error,
    install_deterministic_genval,
    mutate_first_keygen_case,
    session_request,
)


CERTIFICATION = {
    "moduleUrl": "/acvp/v1/modules/1",
    "oeUrl": "/acvp/v1/oes/1",
    "algorithmPrerequisites": [],
}


def envelope(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [{"acvVersion": "1.0"}, payload]


def create_session(client: TestClient, *, auto_generate: bool = True, **extra: Any) -> Dict[str, Any]:
    request = session_request("keyGen", auto_generate=auto_generate)
    request.update(extra)
    response = client.post("/acvp/v1/testSessions", json=envelope(request))
    assert response.status_code == 200
    return body(response)


def pass_session(client: TestClient) -> Dict[str, Any]:
    created = create_session(client)
    expected = body(client.get(f"{created['vectorSetUrls'][0]}/expected"))
    response = client.post(created["vectorSetUrls"][0] + "/results", json=envelope(expected))
    assert response.status_code == 204
    return created


def test_all_pass_session_can_put_certification_and_poll_persistently(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = pass_session(client)
        session_url = f"/acvp/v1/testSessions/{created['testSessionId']}"
        submitted = client.put(session_url, json=envelope(CERTIFICATION))
        assert submitted.status_code == 200
        request_resource = body(submitted)
        assert request_resource["status"] == "initial"
        assert request_resource["url"].startswith("/acvp/v1/requests/")
        assert "external validation authority" in request_resource["message"]
        assert not ({"certificate", "validationId", "approvedUrl"} & set(request_resource))

        repeated = client.put(session_url, json=envelope(CERTIFICATION))
        assert repeated.status_code == 200
        assert body(repeated) == request_resource
        first_poll = body(client.get(request_resource["url"]))
        second_poll = body(client.get(request_resource["url"]))
        assert first_poll == second_poll == request_resource

        conflicting = deepcopy(CERTIFICATION)
        conflicting["oeUrl"] = "/acvp/v1/oes/2"
        conflict = client.put(session_url, json=envelope(conflicting))
        assert conflict.status_code == 409
        assert error(conflict)["code"] == "CERTIFICATION_REQUEST_CONFLICT"

        persisted = get_acvp_request(int(request_resource["url"].rsplit("/", 1)[-1]))
        assert persisted is not None
        assert persisted["testSessionId"] == created["testSessionId"]
        assert persisted["certification"] == CERTIFICATION

    with TestClient(app) as restarted_client:
        assert body(restarted_client.get(request_resource["url"])) == request_resource


def test_certification_rejects_no_vectors_incomplete_and_failed_sessions(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        no_vectors = create_session(client, auto_generate=False)
        no_vectors_response = client.put(
            f"/acvp/v1/testSessions/{no_vectors['testSessionId']}",
            json=envelope(CERTIFICATION),
        )
        assert error(no_vectors_response)["code"] == "VECTOR_SETS_NOT_GENERATED"

        incomplete = create_session(client)
        incomplete_response = client.put(
            f"/acvp/v1/testSessions/{incomplete['testSessionId']}",
            json=envelope(CERTIFICATION),
        )
        assert error(incomplete_response)["code"] == "VECTOR_SET_RESULTS_INCOMPLETE"

        failed = create_session(client)
        expected = body(client.get(f"{failed['vectorSetUrls'][0]}/expected"))
        mutate_first_keygen_case(expected)
        assert client.post(
            failed["vectorSetUrls"][0] + "/results", json=envelope(expected)
        ).status_code == 204
        failed_response = client.put(
            f"/acvp/v1/testSessions/{failed['testSessionId']}",
            json=envelope(CERTIFICATION),
        )
        assert error(failed_response)["code"] == "TEST_SESSION_NOT_PASSED"


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({}, "INVALID_ACVP_ENVELOPE"),
        ([{"acvVersion": "2.0"}, CERTIFICATION], "UNSUPPORTED_ACVP_VERSION"),
        ([{"acvVersion": "1.0"}], "INVALID_ACVP_ENVELOPE"),
        (envelope({"oeUrl": "/acvp/v1/oes/1"}), "INVALID_REQUEST"),
        (envelope({"moduleUrl": "/acvp/v1/modules/1"}), "INVALID_REQUEST"),
        (
            envelope({"moduleUrl": "module-1", "oeUrl": "/acvp/v1/oes/1"}),
            "INVALID_REQUEST",
        ),
    ],
)
def test_certification_requires_canonical_envelope_and_reference_schema(
    payload: Any,
    expected_code: str,
) -> None:
    with TestClient(app) as client:
        created = create_session(client, auto_generate=False)
        response = client.put(
            f"/acvp/v1/testSessions/{created['testSessionId']}",
            json=payload,
        )

    assert response.status_code == 400
    assert error(response)["code"] == expected_code


def test_cancelled_and_expired_sessions_cannot_certify_and_cancel_rejects_poll(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        passed = pass_session(client)
        session_url = f"/acvp/v1/testSessions/{passed['testSessionId']}"
        request = body(client.put(session_url, json=envelope(CERTIFICATION)))
        assert client.delete(session_url).status_code == 200
        poll = body(client.get(request["url"]))
        assert poll["status"] == "rejected"
        assert "cancelled" in poll["message"]
        retry = client.put(session_url, json=envelope(CERTIFICATION))
        assert retry.status_code in {409, 410}

        expired = create_session(client, auto_generate=False, expiresInSeconds=0)
        expired_response = client.put(
            f"/acvp/v1/testSessions/{expired['testSessionId']}",
            json=envelope(CERTIFICATION),
        )
        assert expired_response.status_code == 409
        assert error(expired_response)["code"] == "TEST_SESSION_EXPIRED"

        unknown = client.get("/acvp/v1/requests/999999")
        assert unknown.status_code == 404
        assert error(unknown)["code"] == "UNKNOWN_REQUEST"

        serialized = json.dumps([request, poll])
        assert "certificate" not in serialized.lower()
        assert "validationId" not in serialized


def test_local_submit_remains_deprecated_and_is_not_required(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        passed = pass_session(client)
        standard = client.put(
            f"/acvp/v1/testSessions/{passed['testSessionId']}",
            json=envelope(CERTIFICATION),
        )
        assert standard.status_code == 200

        other = pass_session(client)
        local = client.post(f"/acvp/v1/testSessions/{other['testSessionId']}/submit")
        assert local.status_code == 200
        assert local.headers["Deprecation"] == "true"
        local_body = body(local)
        assert local_body["localExtension"] is True
        assert "url" not in local_body
        assert "certificate" not in json.dumps(local_body).lower()
        assert "validationId" not in json.dumps(local_body)
