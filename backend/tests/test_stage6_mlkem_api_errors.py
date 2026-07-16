from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Callable, Dict, Tuple

import pytest
from fastapi.testclient import TestClient

from app.genval import GenValArtifactError, GenValConfigurationError, GenValExecutionError
from app.main import app
from helpers.mlkem_e2e import (
    body,
    error,
    install_deterministic_genval,
    session_request,
    vector_url,
)


def test_schema_failures_are_rejected_before_genval_validate(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", "encapDecap"),
            )
        )
        by_mode: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        for vector_set_id in created["vectorSetIds"]:
            url = vector_url(created["testSessionId"], vector_set_id)
            mode = body(client.get(url))["mode"]
            by_mode[mode] = (url, body(client.get(f"{url}/expected")))

        keygen_url, keygen = by_mode["keyGen"]
        encap_url, encap = by_mode["encapDecap"]
        cases = [
            (keygen_url, _changed(keygen, lambda value: value.update(algorithm="ML-DSA"))),
            (keygen_url, _changed(keygen, lambda value: value.update(revision="FIPS204"))),
            (keygen_url, _changed(keygen, lambda value: value.update(mode="encapDecap"))),
            (keygen_url, _changed(keygen, _remove_first_tg_id)),
            (keygen_url, _changed(keygen, _duplicate_tc_id)),
            (keygen_url, _changed(keygen, _invalid_hex)),
            (keygen_url, _changed(keygen, _wrong_key_length)),
            (encap_url, _changed(encap, _string_test_passed)),
            (keygen_url, _changed(keygen, _wrong_response_shape)),
            (keygen_url, _changed(keygen, lambda value: value.update(unknownField=True))),
        ]

        for url, invalid in cases:
            before = controller.validate_calls
            response = client.post(f"{url}/results", json={"response": invalid})
            assert response.status_code == 400, response.text
            assert error(response)["code"] not in {
                "NIST_GENVAL_NOT_READY",
                "NIST_GENVAL_ARTIFACT_MISSING",
                "NIST_GENVAL_EXECUTION_ERROR",
            }
            assert controller.validate_calls == before


@pytest.mark.parametrize(
    ("exception_type", "expected_code"),
    [
        (GenValConfigurationError, "NIST_GENVAL_NOT_READY"),
        (GenValArtifactError, "NIST_GENVAL_ARTIFACT_MISSING"),
        (GenValExecutionError, "NIST_GENVAL_EXECUTION_ERROR"),
    ],
)
def test_validation_backend_failures_are_distinct_atomic_and_sanitized(
    monkeypatch: Any,
    tmp_path: Any,
    exception_type: type[BaseException],
    expected_code: str,
) -> None:
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(client.post("/acvp/v1/testSessions", json=session_request("keyGen")))
        session_id = created["testSessionId"]
        url = vector_url(session_id, created["vectorSetIds"][0])
        client.get(url)
        expected = body(client.get(f"{url}/expected"))
        before = body(client.get(f"{url}/results"))
        controller.validation_error = exception_type("controlled Stage 6 backend failure")

        failed = client.post(f"{url}/results", json={"response": expected})
        assert failed.status_code == 500
        failure = error(failed)
        assert failure["code"] == expected_code
        serialized = json.dumps(failed.json())
        for forbidden in ("/root/", "/tmp/", "artifactRoot", "runnerDll", "internalProjection"):
            assert forbidden not in serialized

        after = body(client.get(f"{url}/results"))
        assert after == before
        session = body(client.get(f"/acvp/v1/testSessions/{session_id}"))
        assert session["submittedVectorSetCount"] == 0
        assert session["validatedVectorSetCount"] == 0
        assert session["failedVectorSetCount"] == 0


@pytest.mark.parametrize(
    ("exception_type", "expected_code"),
    [
        (GenValConfigurationError, "NIST_GENVAL_NOT_READY"),
        (GenValArtifactError, "NIST_GENVAL_ARTIFACT_MISSING"),
        (GenValExecutionError, "NIST_GENVAL_EXECUTION_ERROR"),
    ],
)
def test_generation_backend_failures_leave_no_partial_vector_set(
    monkeypatch: Any,
    tmp_path: Any,
    exception_type: type[BaseException],
    expected_code: str,
) -> None:
    controller = install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=session_request("keyGen", "encapDecap", auto_generate=False),
            )
        )
        controller.generation_error = exception_type("controlled Stage 6 generation failure")
        generated = client.post(
            f"/acvp/v1/testSessions/{created['testSessionId']}/vectorSets/generate",
            json={},
        )
        assert generated.status_code == 500
        assert error(generated)["code"] == expected_code
        after = body(client.get(f"/acvp/v1/testSessions/{created['testSessionId']}"))
        assert after["status"] == "capabilitiesAccepted"
        assert after["vectorSetIds"] == []
        listed = body(
            client.get(f"/acvp/v1/testSessions/{created['testSessionId']}/vectorSets")
        )
        assert listed["vectorSets"] == []


def _changed(payload: Dict[str, Any], mutation: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    value = deepcopy(payload)
    mutation(value)
    return value


def _remove_first_tg_id(value: Dict[str, Any]) -> None:
    value["testGroups"][0].pop("tgId")


def _duplicate_tc_id(value: Dict[str, Any]) -> None:
    tests = [test for group in value["testGroups"] for test in group["tests"]]
    tests[1]["tcId"] = tests[0]["tcId"]


def _invalid_hex(value: Dict[str, Any]) -> None:
    value["testGroups"][0]["tests"][0]["ek"] = "GG" + value["testGroups"][0]["tests"][0]["ek"][2:]


def _wrong_key_length(value: Dict[str, Any]) -> None:
    value["testGroups"][0]["tests"][0]["ek"] = value["testGroups"][0]["tests"][0]["ek"][:-2]


def _string_test_passed(value: Dict[str, Any]) -> None:
    for group in value["testGroups"]:
        test = group["tests"][0]
        if "testPassed" in test:
            test["testPassed"] = "true"
            return
    raise AssertionError("fixture has no key-check response")


def _wrong_response_shape(value: Dict[str, Any]) -> None:
    value["testGroups"][0]["tests"][0].pop("dk")
