from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from fastapi import Response
from fastapi.responses import JSONResponse

from app.acvp_mldsa.provider import get_mldsa_provider
from app.acvp_protocol import service
from app.acvp_protocol.routes import (
    create_acvp_v1_test_session,
    get_acvp_v1_test_session_vector_set_results,
    submit_acvp_v1_test_session_vector_set_results,
)
from app.genval import GenValConfigurationError
from app.main import app
from app.storage.sqlite_store import ACVP_SKELETON_VECTOR_SET_STORE, save_acvp_vector_set


FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "nist" / "mldsa"
SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"


def test_removed_runtime_endpoints_return_404() -> None:
    for path in (
        "/api/oracle/mldsa/keygen",
        "/api/oracle/mldsa/keygen/expected-results",
        "/api/oracle/mldsa/siggen",
        "/api/oracle/mldsa/sigver",
        "/api/import",
        "/api/import/old-record",
        "/api/validate",
        "/api/report/old-record",
        "/api/demo/acvp/test-sessions",
        "/api/load-sample",
        "/api/sample-data",
    ):
        status, _ = asyncio.run(_asgi_request(path, method="POST"))
        assert status == 404, path


def test_openapi_contains_only_strict_production_surface() -> None:
    paths = set(app.openapi()["paths"])
    assert "/api/health" in paths
    assert all(path == "/api/health" or path.startswith("/acvp/v1/") for path in paths)
    serialized = json.dumps(app.openapi())
    for removed in ("ImportRequest", "DemoAcvp", "MldsaExpectedResults", "MldsaKeygen"):
        assert removed not in serialized


def test_provider_has_no_local_execution_methods() -> None:
    provider = get_mldsa_provider()
    for method in ("generate_" + "vector_sets", "generate_" + "expected_results", "validate_" + "results"):
        assert not hasattr(provider, method)


def test_nist_genval_validates_passed_and_failed_responses_for_all_modes() -> None:
    for mode in ("keyGen", "sigGen", "sigVer"):
        session_id, vector_id = _create_session(mode)
        passed_response = _fixture(mode, "response.pass.json")
        passed = submit_acvp_v1_test_session_vector_set_results(
            session_id,
            vector_id,
            {"response": passed_response},
        )
        assert isinstance(passed, Response)
        assert passed.status_code == 204
        passed_results = _body(get_acvp_v1_test_session_vector_set_results(session_id, vector_id))
        assert passed_results["results"]["disposition"] == "passed"

        failed_session_id, failed_vector_id = _create_session(mode)
        failed_response = _fixture(mode, "response.fail.json")
        failed = submit_acvp_v1_test_session_vector_set_results(
            failed_session_id,
            failed_vector_id,
            {"response": failed_response},
        )
        assert isinstance(failed, Response)
        assert failed.status_code == 204
        failed_results = _body(get_acvp_v1_test_session_vector_set_results(failed_session_id, failed_vector_id))
        assert failed_results["results"]["disposition"] == "fail"


def test_missing_internal_projection_returns_nist_artifact_error() -> None:
    session_id, vector_id = _create_session("keyGen")
    vector = ACVP_SKELETON_VECTOR_SET_STORE[vector_id]
    vector["artifactPaths"].pop("internalProjection")
    save_acvp_vector_set(vector)

    response = submit_acvp_v1_test_session_vector_set_results(
        session_id,
        vector_id,
        {"response": _fixture("keyGen", "response.pass.json")},
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert _body(response)["error"]["code"] == "NIST_GENVAL_ARTIFACT_MISSING"


def test_genval_configuration_failure_does_not_fallback(monkeypatch: Any) -> None:
    class UnavailableGenVal:
        def __init__(self, *_: Any) -> None:
            pass

        def check_registration(self, *_: Any) -> Dict[str, Any]:
            return {"status": "passed"}

        def generate(self, *_: Any) -> Any:
            raise GenValConfigurationError("runner unavailable")

    monkeypatch.setattr(service, "NistCliGenValProvider", UnavailableGenVal)
    response = create_acvp_v1_test_session(
        {"algorithms": [_registration("keyGen")], "campaignSeed": SEED}
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert _body(response)["error"]["code"] == "NIST_GENVAL_NOT_READY"


def _create_session(mode: str) -> Tuple[str, str]:
    created = _body(
        create_acvp_v1_test_session(
            {"algorithms": [_registration(mode)], "campaignSeed": SEED, "isSample": False}
        )
    )
    return created["testSessionId"], created["vectorSetIds"][0]


def _registration(mode: str) -> Dict[str, Any]:
    registration: Dict[str, Any] = {
        "algorithm": "ML-DSA",
        "mode": mode,
        "revision": "FIPS204",
        "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
    }
    if mode == "keyGen":
        registration["parameterSets"] = ["ML-DSA-44"]
        return registration
    registration["signatureInterfaces"] = ["external"]
    registration["preHash"] = ["pure"]
    registration["capabilities"] = [
        {
            "parameterSets": ["ML-DSA-44"],
            "messageLength": [{"min": 8, "max": 128, "increment": 8}],
            "contextLength": [{"min": 0, "max": 64, "increment": 8}],
            "hashAlgs": ["SHA2-256"],
        }
    ]
    if mode == "sigGen":
        registration["deterministic"] = [True]
    return registration


def _fixture(mode: str, name: str) -> Dict[str, Any]:
    return deepcopy(json.loads((FIXTURE_ROOT / mode / name).read_text(encoding="utf-8")))


def _body(value: Any) -> Dict[str, Any]:
    if isinstance(value, JSONResponse):
        value = json.loads(value.body.decode("utf-8"))
    if isinstance(value, list):
        value = value[1]
    assert isinstance(value, dict)
    return value


async def _asgi_request(path: str, *, method: str) -> Tuple[int, bytes]:
    messages = []

    async def receive() -> Dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Dict[str, Any]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("test", 0),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, body
