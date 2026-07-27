from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Dict

from fastapi.testclient import TestClient

from app.main import app
from helpers.mlkem_e2e import (
    FUNCTIONS,
    PARAMETER_SETS,
    body,
    error,
    install_deterministic_genval,
    mutate_encap_functions,
    mutate_first_keygen_case,
    session_request,
    vector_url,
)


def test_keygen_sample_expected_is_only_a_known_good_test_response(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    """Sample expected results are test input only, not an IUT or production oracle."""
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created_response = client.post(
            "/acvp/v1/testSessions",
            json=session_request("keyGen"),
        )
        assert created_response.status_code == 200
        created = body(created_response)
        session_id = created["testSessionId"]
        assert created["status"] == "vectorReady"
        assert len(created["vectorSetIds"]) == len(created["vectorSetUrls"]) == 1
        vector_set_id = created["vectorSetIds"][0]
        url = vector_url(session_id, vector_set_id)
        assert created["vectorSetUrls"] == [url]

        session = body(client.get(f"/acvp/v1/testSessions/{session_id}"))
        vector_summary = session["vectorSets"][0]
        assert vector_summary["provider"] == "nist-genval"
        assert vector_summary["providerName"] == "NIST ACVP-Server GenValAppRunner"
        assert vector_summary["hasInternalProjection"] is True
        assert "artifactPaths" not in vector_summary
        assert "internalProjection" not in json.dumps(session)

        listed = body(client.get(f"/acvp/v1/testSessions/{session_id}/vectorSets"))
        assert listed["vectorSetUrls"] == [url]
        assert listed["vectorSets"][0]["vectorSetId"] == vector_set_id

        prompt = body(client.get(url))
        assert (prompt["algorithm"], prompt["mode"], prompt["revision"]) == (
            "ML-KEM",
            "keyGen",
            "FIPS203",
        )
        assert {group["parameterSet"] for group in prompt["testGroups"]} == set(PARAMETER_SETS)
        assert all(
            {"tcId", "d", "z"} <= set(test)
            for group in prompt["testGroups"]
            for test in group["tests"]
        )
        assert "internalProjection" not in json.dumps(prompt)

        expected_response = client.get(f"{url}/expected")
        assert expected_response.status_code == 200
        known_good_test_response = deepcopy(body(expected_response))
        submit = client.post(f"{url}/results", json={"response": known_good_test_response})
        assert submit.status_code == 204
        assert controller.validate_calls == 1

        results = body(client.get(f"{url}/results"))["results"]
        assert results["disposition"] == "passed"
        assert results["tests"]
        assert {test["result"] for test in results["tests"]} == {"passed"}

        # Exercise the still-public replacement endpoint with the same known-good test input.
        update = client.put(f"{url}/results", json={"response": known_good_test_response})
        assert update.status_code == 204
        assert controller.validate_calls == 2

        aggregate = body(client.get(f"/acvp/v1/testSessions/{session_id}/results"))
        assert aggregate["passed"] is True
        assert aggregate["results"] == [
            {"vectorSetUrl": url, "status": "passed", "disposition": "passed"}
        ]
        finalized = body(client.post(f"/acvp/v1/testSessions/{session_id}/submit"))
        assert finalized["status"] == "validated"
        assert finalized["summary"]["sessionPassed"] is True
        history = {entry["to"] for entry in finalized["stateHistory"]}
        assert {"resultsSubmitted", "validating", "validated"} <= history


def test_encap_decap_sample_pass_and_function_specific_crypto_failures(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    """Known-good sample input and schema-valid mutations cross the GenVal boundary."""
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(client.post("/acvp/v1/testSessions", json=session_request("encapDecap")))
        session_id = created["testSessionId"]
        vector_set_id = created["vectorSetIds"][0]
        url = vector_url(session_id, vector_set_id)

        prompt = body(client.get(url))
        assert {group["parameterSet"] for group in prompt["testGroups"]} == set(PARAMETER_SETS)
        assert {group["function"] for group in prompt["testGroups"]} == set(FUNCTIONS)
        expected_test_types = {
            "encapsulation": "AFT",
            "decapsulation": "VAL",
            "encapsulationKeyCheck": "VAL",
            "decapsulationKeyCheck": "VAL",
        }
        assert all(
            group["testType"] == expected_test_types[group["function"]]
            for group in prompt["testGroups"]
        )
        assert "expectedResults" not in json.dumps(prompt)

        expected = body(client.get(f"{url}/expected"))
        assert client.post(f"{url}/results", json={"response": deepcopy(expected)}).status_code == 204
        passed = body(client.get(f"{url}/results"))["results"]
        assert passed["disposition"] == "passed"

        schema_valid_but_wrong = deepcopy(expected)
        changed = mutate_encap_functions(prompt, schema_valid_but_wrong)
        assert client.put(f"{url}/results", json={"response": schema_valid_but_wrong}).status_code == 204
        failed = body(client.get(f"{url}/results"))["results"]
        assert failed["disposition"] == "fail"
        failed_tc_ids = {test["tcId"] for test in failed["tests"] if test["result"] == "fail"}
        assert set(changed.values()) <= failed_tc_ids
        assert controller.validate_calls == 2


def test_explicit_generation_is_single_use_and_failure_is_atomic(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", auto_generate=False),
            )
        )
        session_id = created["testSessionId"]
        assert created["status"] == "capabilitiesAccepted"
        assert created["vectorSetIds"] == created["vectorSetUrls"] == []

        generated_response = client.post(
            f"/acvp/v1/testSessions/{session_id}/vectorSets/generate",
            json={"testsPerGroup": 1},
        )
        assert generated_response.status_code == 200
        generated = body(generated_response)
        assert generated["status"] == "vectorReady"
        assert len(generated["vectorSetIds"]) == 1

        duplicate = client.post(
            f"/acvp/v1/testSessions/{session_id}/vectorSets/generate",
            json={},
        )
        assert duplicate.status_code == 409
        assert error(duplicate)["code"] == "VECTOR_SETS_ALREADY_GENERATED"

        second = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", "encapDecap", auto_generate=False),
            )
        )
        from app.genval import GenValExecutionError

        controller.generation_error = GenValExecutionError("injected GenVal execution error")
        failed_generation = client.post(
            f"/acvp/v1/testSessions/{second['testSessionId']}/vectorSets/generate",
            json={},
        )
        assert failed_generation.status_code == 500
        after = body(client.get(f"/acvp/v1/testSessions/{second['testSessionId']}"))
        assert after["status"] == "capabilitiesAccepted"
        assert after["vectorSetIds"] == []


def test_keygen_schema_valid_crypto_failure_is_reported_by_validation(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(client.post("/acvp/v1/testSessions", json=session_request("keyGen")))
        url = vector_url(created["testSessionId"], created["vectorSetIds"][0])
        client.get(url)
        wrong = deepcopy(body(client.get(f"{url}/expected")))
        changed_tc_id = mutate_first_keygen_case(wrong)
        submit = client.post(f"{url}/results", json={"response": wrong})
        assert submit.status_code == 204
        assert controller.validate_calls == 1
        results = body(client.get(f"{url}/results"))["results"]
        assert results["disposition"] == "fail"
        assert changed_tc_id in {
            test["tcId"] for test in results["tests"] if test["result"] == "fail"
        }


def test_non_sample_boundary_hides_expected_and_internal_artifacts(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", is_sample=False),
            )
        )
        session_id = created["testSessionId"]
        url = vector_url(session_id, created["vectorSetIds"][0])
        prompt_response = client.get(url)
        assert prompt_response.status_code == 200
        prompt = body(prompt_response)
        assert prompt["isSample"] is False

        denied = client.get(f"{url}/expected")
        assert denied.status_code == 403
        assert error(denied)["code"] == "EXPECTED_RESULTS_NOT_AVAILABLE"
        bypass = client.get(f"{url}/results", params={"showExpected": "true"})
        assert bypass.status_code == 403
        public_text = "\n".join(
            json.dumps(response.json())
            for response in (prompt_response, denied, bypass, client.get(f"/acvp/v1/testSessions/{session_id}"))
        )
        for forbidden in ("expectedResults", "internalProjection", "artifactPaths", "/root/"):
            assert forbidden not in public_text


def test_two_mode_session_aggregate_incomplete_failed_passed_and_finalized(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", "encapDecap"),
            )
        )
        session_id = created["testSessionId"]
        assert len(created["vectorSetIds"]) == len(created["vectorSetUrls"]) == 2
        vectors: Dict[str, Dict[str, Any]] = {}
        for vector_set_id in created["vectorSetIds"]:
            url = vector_url(session_id, vector_set_id)
            prompt = body(client.get(url))
            vectors[prompt["mode"]] = {
                "url": url,
                "prompt": prompt,
                "expected": body(client.get(f"{url}/expected")),
            }

        keygen = vectors["keyGen"]
        assert client.post(f"{keygen['url']}/results", json={"response": keygen["expected"]}).status_code == 204
        incomplete = client.post(f"/acvp/v1/testSessions/{session_id}/submit")
        assert incomplete.status_code == 409
        assert error(incomplete)["code"] == "VECTOR_SET_RESULTS_INCOMPLETE"

        encap = vectors["encapDecap"]
        failed_response = deepcopy(encap["expected"])
        mutate_encap_functions(encap["prompt"], failed_response)
        assert client.post(f"{encap['url']}/results", json={"response": failed_response}).status_code == 204
        aggregate = body(client.get(f"/acvp/v1/testSessions/{session_id}/results"))
        assert aggregate["passed"] is False
        assert {item["disposition"] for item in aggregate["results"]} == {"passed", "fail"}

        submitted = body(client.post(f"/acvp/v1/testSessions/{session_id}/submit"))
        assert submitted["status"] == "failed"
        assert submitted["summary"]["failedVectorSets"] == 1
        assert body(client.post(f"/acvp/v1/testSessions/{session_id}/submit"))["status"] == "failed"
        finalized_update = client.put(
            f"{keygen['url']}/results",
            json={"response": keygen["expected"]},
        )
        assert finalized_update.status_code == 409
        assert error(finalized_update)["code"] == "VECTOR_SET_ALREADY_FINALIZED"

        all_pass = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", "encapDecap"),
            )
        )
        for vector_set_id in all_pass["vectorSetIds"]:
            url = vector_url(all_pass["testSessionId"], vector_set_id)
            client.get(url)
            expected = body(client.get(f"{url}/expected"))
            assert client.post(f"{url}/results", json={"response": expected}).status_code == 204
        all_pass_submit = body(
            client.post(f"/acvp/v1/testSessions/{all_pass['testSessionId']}/submit")
        )
        assert all_pass_submit["status"] == "validated"
        assert all_pass_submit["summary"]["sessionPassed"] is True

def test_validation_report_artifacts_are_persisted_and_queryable(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)

    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen"),
            )
        )
        session_id = created["testSessionId"]
        url = vector_url(session_id, created["vectorSetIds"][0])

        client.get(url)
        expected = body(client.get(f"{url}/expected"))

        unavailable = client.get(f"{url}/reports")
        assert unavailable.status_code == 409
        assert error(unavailable)["code"] == "REPORT_NOT_AVAILABLE"

        submitted = client.post(
            f"{url}/results",
            json={"response": deepcopy(expected)},
        )
        assert submitted.status_code == 204

        first_store = body(client.get(f"{url}/reports"))
        first_report = first_store["report"]
        first_report_id = first_report["reportId"]

        assert first_store["reportCount"] == 1
        assert first_store["latestReportId"] == first_report_id
        assert first_report["artifactType"] == "acvp-validation-report"
        assert first_report["schemaVersion"] == "1.0"
        assert first_report["testSessionId"] == session_id
        assert first_report["vsId"] == expected["vsId"]
        assert first_report["algorithm"] == "ML-KEM"
        assert first_report["revision"] == "FIPS203"
        assert first_report["mode"] == "keyGen"
        serialized_report = json.dumps(first_store)
        for forbidden in (
            "vectorSetId",
            "artifactPaths",
            "internalProjection",
            "expectedResults",
        ):
            assert forbidden not in serialized_report
        assert first_report["disposition"] == "passed"
        assert first_report["passed"] is True
        assert first_report["publishable"] is True
        assert first_report["summary"]["failed"] == 0
        assert len(first_report["responseSha256"]) == 64
        assert len(first_report["artifactSha256"]) == 64
        assert "not a NIST/CAVP validation certificate" in first_report["disclaimer"]

        wrong = deepcopy(expected)
        changed_tc_id = mutate_first_keygen_case(wrong)

        updated = client.put(
            f"{url}/results",
            json={"response": wrong},
        )
        assert updated.status_code == 204

        second_store = body(client.get(f"{url}/reports"))
        second_report = second_store["report"]

        assert second_store["reportCount"] == 2
        assert second_store["latestReportId"] == second_report["reportId"]
        assert second_report["reportId"] != first_report_id
        assert second_report["disposition"] == "fail"
        assert second_report["passed"] is False
        assert second_report["publishable"] is False
        assert second_report["summary"]["failed"] >= 1
        assert any(
            failed_test["tcId"] == changed_tc_id
            for group in second_report["testGroups"]
            for failed_test in group["failedTests"]
        )

        historical = body(
            client.get(
                f"{url}/reports",
                params={"reportId": first_report_id},
            )
        )
        assert historical["reportCount"] == 2
        assert historical["report"]["reportId"] == first_report_id
        assert historical["report"]["disposition"] == "passed"
