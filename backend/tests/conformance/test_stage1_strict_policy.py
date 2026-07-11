from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Dict

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.acvp_core.bootstrap import build_algorithm_registry
from app.acvp_protocol.routes import (
    _parse_session_create_request,
    _parse_vector_set_generate_request,
    create_acvp_v1_test_session,
    generate_acvp_v1_test_session_vector_sets,
    get_acvp_v1_test_session,
    get_acvp_v1_test_session_vector_set_expected,
    get_acvp_v1_test_session_vector_set_results,
    get_acvp_v1_version,
    submit_acvp_v1_test_session_vector_set_results,
)
from app.main import acvp_request_id_middleware, app
from app.storage.sqlite_store import (
    ACVP_SKELETON_SESSION_STORE,
    ACVP_SKELETON_VECTOR_SET_STORE,
    save_acvp_session,
    save_acvp_vector_set,
)


CAMPAIGN_SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"
REGISTRY = build_algorithm_registry()


def test_openapi_and_route_signatures_expose_no_profile_parameters() -> None:
    schema = app.openapi()
    serialized = json.dumps(schema)

    assert "workflowProfile" not in serialized
    assert "generationProfile" not in serialized
    for endpoint in (
        create_acvp_v1_test_session,
        get_acvp_v1_version,
        submit_acvp_v1_test_session_vector_set_results,
    ):
        assert "workflowProfile" not in inspect.signature(endpoint).parameters


def test_forbidden_profile_query_is_rejected_by_central_middleware() -> None:
    for query, code in (
        (b"workflowProfile=local", "WORKFLOW_PROFILE_NOT_SUPPORTED"),
        (b"generationProfile=local-debug", "GENERATION_PROFILE_NOT_SUPPORTED"),
    ):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/acvp/v1/version",
                "query_string": query,
                "headers": [],
            }
        )
        response = asyncio.run(acvp_request_id_middleware(request, _unexpected_next))
        assert response.status_code == 400
        assert _body(response)["error"]["code"] == code


async def _unexpected_next(_: Request) -> Any:
    raise AssertionError("Forbidden query must be rejected before routing.")


def test_request_body_rejects_removed_controls_with_explicit_codes() -> None:
    rejected = {
        "prompt": "STRICT_REGISTRATION_REQUIRED",
        "autoGenerateExpectedResults": "AUTO_EXPECTED_RESULTS_NOT_SUPPORTED",
        "generationProfile": "GENERATION_PROFILE_NOT_SUPPORTED",
        "workflowPolicy": "CLIENT_POLICY_NOT_SUPPORTED",
        "executionBackend": "CLIENT_POLICY_NOT_SUPPORTED",
    }
    for field, code in rejected.items():
        payload: Dict[str, Any] = {"algorithms": [_keygen_registration()], field: True}
        if field == "generationProfile":
            payload[field] = "local-debug"
        if field == "prompt":
            payload[field] = {"vsId": 1}
        parsed = _parse_session_create_request(payload)
        assert isinstance(parsed, JSONResponse)
        assert _body(parsed)["error"]["code"] == code

    generated = _parse_vector_set_generate_request({"generationProfile": "local-debug"})
    assert isinstance(generated, JSONResponse)
    assert _body(generated)["error"]["code"] == "GENERATION_PROFILE_NOT_SUPPORTED"


def test_new_session_and_vectors_are_strict_nist_only() -> None:
    created = _body(
        create_acvp_v1_test_session(
            {
                "algorithms": [_keygen_registration()],
                "campaignSeed": CAMPAIGN_SEED,
                "isSample": False,
            },
            REGISTRY,
        )
    )
    vector_id = created["vectorSetIds"][0]
    session = ACVP_SKELETON_SESSION_STORE[created["testSessionId"]]
    vector = ACVP_SKELETON_VECTOR_SET_STORE[vector_id]

    assert created["workflowPolicy"] == "strict"
    assert created["executionBackend"] == "nist-genval"
    assert session["workflowPolicy"] == "strict"
    assert session["executionBackend"] == "nist-genval"
    assert vector["workflowPolicy"] == "strict"
    assert vector["executionBackend"] == "nist-genval"
    assert vector["provider"] == "nist-genval"
    assert "generationProfile" not in created
    assert "workflowProfile" not in created


def test_expected_results_are_hidden_for_non_sample_and_available_for_sample() -> None:
    non_sample = _body(
        create_acvp_v1_test_session(
            {"algorithms": [_keygen_registration()], "campaignSeed": CAMPAIGN_SEED, "isSample": False},
            REGISTRY,
        )
    )
    denied = get_acvp_v1_test_session_vector_set_expected(
        non_sample["testSessionId"], non_sample["vectorSetIds"][0]
    )
    assert isinstance(denied, JSONResponse)
    assert denied.status_code == 403
    assert _body(denied)["error"]["code"] == "EXPECTED_RESULTS_NOT_AVAILABLE"
    show_expected = get_acvp_v1_test_session_vector_set_results(
        non_sample["testSessionId"], non_sample["vectorSetIds"][0], showExpected=True
    )
    assert isinstance(show_expected, JSONResponse)
    assert show_expected.status_code == 403
    assert _body(show_expected)["error"]["code"] == "EXPECTED_RESULTS_NOT_AVAILABLE"

    sample = _body(
        create_acvp_v1_test_session(
            {"algorithms": [_keygen_registration()], "campaignSeed": CAMPAIGN_SEED, "isSample": True},
            REGISTRY,
        )
    )
    expected = _body(
        get_acvp_v1_test_session_vector_set_expected(sample["testSessionId"], sample["vectorSetIds"][0])
    )
    assert expected["algorithm"] == "ML-DSA"
    assert expected["mode"] == "keyGen"


def test_legacy_local_sessions_are_readable_but_cannot_generate_or_validate() -> None:
    session_id = "legacy-local-session"
    vector_id = "legacy-local-vector"
    save_acvp_session(
        {
            "testSessionId": session_id,
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-01T00:00:00+00:00",
            "status": "vectorReady",
            "vectorSetIds": [vector_id],
            "vectorSetUrls": [f"/acvp/v1/testSessions/{session_id}/vectorSets/{vector_id}"],
            "workflowProfile": "local",
            "stateHistory": [],
        }
    )
    save_acvp_vector_set(
        {
            "vectorSetId": vector_id,
            "testSessionId": session_id,
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-01T00:00:00+00:00",
            "status": "ready",
            "prompt": {"vsId": 1, "algorithm": "ML-DSA", "mode": "keyGen", "revision": "FIPS204", "testGroups": []},
            "expectedResults": {"vsId": 1, "algorithm": "ML-DSA", "mode": "keyGen", "revision": "FIPS204", "testGroups": []},
            "stateHistory": [],
        }
    )

    blocked = submit_acvp_v1_test_session_vector_set_results(
        session_id,
        vector_id,
        {"response": {"vsId": 1, "algorithm": "ML-DSA", "mode": "keyGen", "revision": "FIPS204", "testGroups": []}},
        REGISTRY,
    )
    assert isinstance(blocked, JSONResponse)
    assert blocked.status_code == 409
    assert _body(blocked)["error"]["code"] == "LEGACY_LOCAL_SESSION_NOT_SUPPORTED"
    generated = generate_acvp_v1_test_session_vector_sets(session_id, {}, REGISTRY)
    assert isinstance(generated, JSONResponse)
    assert generated.status_code == 409
    assert _body(generated)["error"]["code"] == "LEGACY_LOCAL_SESSION_NOT_SUPPORTED"
    detail = _body(get_acvp_v1_test_session(session_id))
    assert detail["legacy"] is True
    assert detail["legacyStatus"] == "unsupported"


def test_environment_profile_cannot_change_fixed_policy(monkeypatch: Any) -> None:
    monkeypatch.setenv("ACVP_WORKFLOW_PROFILE", "local")
    body = _body(get_acvp_v1_version())
    assert body["workflowPolicy"] == "strict"
    assert body["executionBackend"] == "nist-genval"


def _keygen_registration() -> Dict[str, Any]:
    return {
        "algorithm": "ML-DSA",
        "mode": "keyGen",
        "revision": "FIPS204",
        "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
        "parameterSets": ["ML-DSA-44"],
    }


def _body(value: Any) -> Dict[str, Any]:
    if isinstance(value, JSONResponse):
        value = json.loads(value.body.decode("utf-8"))
    if isinstance(value, list):
        assert value[0] == {"acvVersion": "1.0"}
        assert isinstance(value[1], dict)
        return value[1]
    assert isinstance(value, dict)
    return value
