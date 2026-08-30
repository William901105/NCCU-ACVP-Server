from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.acvp_protocol.report_pdf import render_validation_report_pdf
from helpers.mlkem_e2e import body, error, install_deterministic_genval, session_request


CERTIFICATION = {
    "moduleUrl": "/acvp/v1/modules/report-module",
    "oeUrl": "/acvp/v1/oes/report-oe",
    "algorithmPrerequisites": [],
}


def envelope(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"acvVersion": "1.0"}, payload]


def test_complete_validation_report_is_persisted_and_downloaded_as_pdf(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = body(
            client.post(
                "/acvp/v1/testSessions",
                json=envelope(session_request("keyGen")),
            )
        )
        session_id = created["testSessionId"]
        vector_url = created["vectorSetUrls"][0]
        vs_id = created["vectorSetIds"][0]

        unavailable = client.get(f"/acvp/v1/testSessions/{session_id}/reports/pdf")
        assert unavailable.status_code == 409
        assert error(unavailable)["code"] == "REPORT_NOT_AVAILABLE"

        prompt = body(client.get(vector_url))
        iut_response = body(client.get(f"{vector_url}/expected"))
        assert client.post(
            f"{vector_url}/results",
            json=envelope(iut_response),
        ).status_code == 204

        artifact_response = client.get(f"{vector_url}/reports")
        assert artifact_response.status_code == 200
        artifact_body = body(artifact_response)
        assert artifact_body["reportCount"] == 1
        artifact = artifact_body["report"]
        assert artifact["artifactType"] == "nccu-acvp-validation-report"
        assert artifact["vsId"] == vs_id
        assert artifact["disposition"] == "passed"
        assert len(artifact["responseSha256"]) == 64
        assert len(artifact["artifactSha256"]) == 64

        certification = client.put(
            f"/acvp/v1/testSessions/{session_id}",
            json=envelope(CERTIFICATION),
        )
        assert certification.status_code == 200

        report_response = client.get(f"/acvp/v1/testSessions/{session_id}/reports")
        assert report_response.status_code == 200
        report = body(report_response)
        assert report["summary"]["sessionPassed"] is True
        assert report["certificationRequest"]["requestPayload"] == CERTIFICATION
        assert len(report["vectorSets"]) == 1
        vector_report = report["vectorSets"][0]
        assert vector_report["prompt"] == prompt
        assert vector_report["iutResponse"] == iut_response
        assert vector_report["validationResults"]["results"]["tests"]

        serialized = json.dumps(report)
        assert "expectedResults" not in serialized
        assert '"internalProjection":' not in serialized

        pdf_response = client.get(f"/acvp/v1/testSessions/{session_id}/reports/pdf")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"] == "application/pdf"
        assert "attachment" in pdf_response.headers["content-disposition"]
        assert session_id in pdf_response.headers["content-disposition"]
        assert pdf_response.content.startswith(b"%PDF-1.4")
        assert b"NCCU ACVP Validation Report" in pdf_response.content
        assert b"VALIDATION SUMMARY" in pdf_response.content
        assert b"VECTOR SET 1" in pdf_response.content
        assert b"Overall result: PASSED" in pdf_response.content
        assert b"validationResults" not in pdf_response.content
        assert b"iutResponse" not in pdf_response.content
        assert b"expectedResults" not in pdf_response.content
        assert pdf_response.content.rstrip().endswith(b"%%EOF")


def test_pdf_renderer_paginates_basic_information_without_raw_json() -> None:
    marker = "RAW-JSON-MARKER-MUST-NOT-APPEAR"
    report = {
        "reportId": "REPORT-UNIT",
        "testSessionId": "session-unit",
        "generatedAt": "2026-08-20T00:00:00+00:00",
        "session": {"status": "validated"},
        "summary": {
            "sessionPassed": True,
            "totalVectorSets": 1,
            "passedVectorSets": 1,
            "failedVectorSets": 0,
        },
        "certificationRequest": None,
        "vectorSets": [
            {
                "metadata": {
                    "vsId": index,
                    "algorithm": "ML-KEM",
                    "revision": "FIPS203",
                    "mode": "keyGen",
                    "status": "validated",
                    "testGroupCount": 1,
                    "validatedAt": "2026-08-20T00:00:00+00:00",
                    "providerName": "NIST GenVal",
                },
                "prompt": {
                    "testGroups": [
                        {"parameterSet": "ML-KEM-512", "testType": "AFT"}
                    ],
                    "rawMarker": marker,
                },
                "iutResponse": {"rawMarker": marker},
                "validationResults": {
                    "results": {
                        "disposition": "passed",
                        "tests": [{"tcId": 1, "result": "passed"}],
                    }
                },
            }
            for index in range(30)
        ],
        "disclaimer": "Local validation report.",
    }

    pdf = render_validation_report_pdf(report)

    assert pdf.startswith(b"%PDF-1.4")
    assert marker.encode("ascii") not in pdf
    assert b"Algorithm: ML-KEM" in pdf
    assert b"Passed test cases: 1" in pdf
    assert b"/Count " in pdf
    assert b"Page 2 of" in pdf
    assert pdf.rstrip().endswith(b"%%EOF")
