from __future__ import annotations

from copy import deepcopy
import json
import os
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.main import app
from helpers.mlkem_e2e import (
    FUNCTIONS,
    PARAMETER_SETS,
    body,
    error,
    mutate_encap_functions,
    mutate_first_keygen_case,
    session_request,
    vector_url,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("NCCU_ACVP_LIVE_GENVAL") != "1",
    reason="set NCCU_ACVP_LIVE_GENVAL=1 to execute the vendored NIST GenVal runtime",
)


def test_live_keygen_generation_pass_and_cryptographic_failure(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    """Sample expected results are known-good test input, not an IUT or production oracle."""
    _use_isolated_artifacts(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(client.post("/acvp/v1/testSessions", json=session_request("keyGen")))
        assert created["status"] == "vectorReady"
        url = vector_url(created["testSessionId"], created["vectorSetIds"][0])
        prompt = body(client.get(url))
        assert {group["parameterSet"] for group in prompt["testGroups"]} == set(PARAMETER_SETS)
        expected = body(client.get(f"{url}/expected"))

        assert client.post(f"{url}/results", json={"response": deepcopy(expected)}).status_code == 204
        passed = body(client.get(f"{url}/results"))["results"]
        assert passed["disposition"] == "passed"
        assert {test["result"] for test in passed["tests"]} == {"passed"}

        wrong = deepcopy(expected)
        changed_tc_id = mutate_first_keygen_case(wrong)
        assert client.put(f"{url}/results", json={"response": wrong}).status_code == 204
        failed = body(client.get(f"{url}/results"))["results"]
        assert failed["disposition"] == "fail"
        assert changed_tc_id in {
            test["tcId"] for test in failed["tests"] if test["result"] == "fail"
        }
        summary = body(client.get(f"/acvp/v1/testSessions/{created['testSessionId']}"))
        assert summary["failedVectorSetCount"] == 1
        assert summary["vectorSets"][0]["provider"] == "nist-genval"
        assert summary["vectorSets"][0]["providerName"] == "NIST ACVP-Server GenValAppRunner"


def test_live_encap_decap_pass_and_four_function_failure_parity(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    """NIST GenVal, rather than local comparison, decides all four function failures."""
    _use_isolated_artifacts(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(client.post("/acvp/v1/testSessions", json=session_request("encapDecap")))
        url = vector_url(created["testSessionId"], created["vectorSetIds"][0])
        prompt = body(client.get(url))
        assert {group["function"] for group in prompt["testGroups"]} == set(FUNCTIONS)
        expected = body(client.get(f"{url}/expected"))
        assert client.post(f"{url}/results", json={"response": deepcopy(expected)}).status_code == 204
        assert body(client.get(f"{url}/results"))["results"]["disposition"] == "passed"

        wrong = deepcopy(expected)
        changed = mutate_encap_functions(prompt, wrong)
        assert client.put(f"{url}/results", json={"response": wrong}).status_code == 204
        failed = body(client.get(f"{url}/results"))["results"]
        assert failed["disposition"] == "fail"
        failed_tc_ids = {test["tcId"] for test in failed["tests"] if test["result"] == "fail"}
        assert set(changed.values()) <= failed_tc_ids


def test_live_sample_non_sample_and_two_mode_session_aggregate(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    _use_isolated_artifacts(monkeypatch, tmp_path)
    with TestClient(app) as client:
        non_sample = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", is_sample=False),
            )
        )
        non_sample_url = vector_url(non_sample["testSessionId"], non_sample["vectorSetIds"][0])
        prompt_response = client.get(non_sample_url)
        assert body(prompt_response)["isSample"] is False
        denied = client.get(f"{non_sample_url}/expected")
        assert denied.status_code == 403
        assert error(denied)["code"] == "EXPECTED_RESULTS_NOT_AVAILABLE"
        assert client.get(f"{non_sample_url}/results", params={"showExpected": "true"}).status_code == 403
        assert "internalProjection" not in json.dumps(denied.json())

        aggregate = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", "encapDecap"),
            )
        )
        vectors: Dict[str, Dict[str, Any]] = {}
        for vector_set_id in aggregate["vectorSetIds"]:
            url = vector_url(aggregate["testSessionId"], vector_set_id)
            prompt = body(client.get(url))
            vectors[prompt["mode"]] = {
                "url": url,
                "prompt": prompt,
                "expected": body(client.get(f"{url}/expected")),
            }

        keygen = vectors["keyGen"]
        assert client.post(f"{keygen['url']}/results", json={"response": keygen["expected"]}).status_code == 204
        incomplete = client.post(f"/acvp/v1/testSessions/{aggregate['testSessionId']}/submit")
        assert incomplete.status_code == 409
        assert error(incomplete)["code"] == "VECTOR_SET_RESULTS_INCOMPLETE"

        encap = vectors["encapDecap"]
        wrong = deepcopy(encap["expected"])
        mutate_encap_functions(encap["prompt"], wrong)
        assert client.post(f"{encap['url']}/results", json={"response": wrong}).status_code == 204
        session_results = body(
            client.get(f"/acvp/v1/testSessions/{aggregate['testSessionId']}/results")
        )
        assert session_results["passed"] is False
        assert {item["disposition"] for item in session_results["results"]} == {"passed", "fail"}
        finalized = body(client.post(f"/acvp/v1/testSessions/{aggregate['testSessionId']}/submit"))
        assert finalized["status"] == "failed"
        assert finalized["summary"]["failedVectorSets"] == 1


@pytest.mark.skipif(
    os.environ.get("NCCU_ACVP_LIVE_GENVAL_UNAVAILABLE") != "1",
    reason="run separately with Orleans stopped and NCCU_ACVP_LIVE_GENVAL_UNAVAILABLE=1",
)
def test_live_orleans_unavailable_is_bounded_atomic_and_sanitized(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    _use_isolated_artifacts(monkeypatch, tmp_path)
    monkeypatch.setenv("ACVP_GENVAL_TIMEOUT_SECONDS", "5")
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", auto_generate=False),
            )
        )
        response = client.post(
            f"/acvp/v1/testSessions/{created['testSessionId']}/vectorSets/generate",
            json={},
        )
        assert response.status_code == 500
        failure = error(response)
        assert failure["code"] == "NIST_GENVAL_EXECUTION_ERROR"
        serialized = json.dumps(response.json())
        for forbidden in ("/root/", "/tmp/", "runnerDll", "artifactRoot", "internalProjection"):
            assert forbidden not in serialized
        after = body(client.get(f"/acvp/v1/testSessions/{created['testSessionId']}"))
        assert after["status"] == "capabilitiesAccepted"
        assert after["vectorSetIds"] == []


def _use_isolated_artifacts(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("ACVP_GENVAL_ARTIFACT_ROOT", str(tmp_path / "genval-artifacts"))
