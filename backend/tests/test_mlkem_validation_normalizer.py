from __future__ import annotations

from app.algorithms.mlkem.validation_normalizer import normalize_nist_validation


def test_normalizer_reports_all_passed_results_and_prompt_metadata() -> None:
    validation = {
        "vsId": 42,
        "disposition": "passed",
        "tests": [
            {"tgId": 1, "tcId": 1, "result": "passed"},
            {"tgId": 1, "tcId": 2, "result": "PASSED"},
        ],
    }
    prompt = {
        "vsId": 42,
        "algorithm": "ML-KEM",
        "mode": "keyGen",
        "revision": "FIPS203",
        "testGroups": [],
    }
    normalized = normalize_nist_validation(validation, prompt=prompt)

    assert normalized["metadata"] == {
        "vsId": 42,
        "algorithm": "ML-KEM",
        "mode": "keyGen",
        "revision": "FIPS203",
        "provider": "nist-genval",
        "validationDisposition": "passed",
    }
    assert normalized["summary"] == {
        "total": 2,
        "passed": 2,
        "failed": 0,
        "missing": 0,
        "malformed": 0,
        "extra": 0,
    }
    assert normalized["failures"] == []
    assert all(case["status"] == "passed" for case in normalized["caseResults"])


def test_normalizer_preserves_partial_failure_reason_and_nist_result() -> None:
    failed = {"tgId": 2, "tcId": 9, "result": "failed", "reason": "k mismatch"}
    validation = {
        "disposition": "failed",
        "tests": [{"tgId": 2, "tcId": 8, "result": "passed"}, failed],
    }
    normalized = normalize_nist_validation(validation)

    assert normalized["summary"]["passed"] == 1
    assert normalized["summary"]["failed"] == 1
    assert normalized["failures"][0] == {
        "tgId": 2,
        "tcId": 9,
        "field": "result",
        "reason": "k mismatch",
        "expected": "passed",
        "provided": "failed",
    }
    assert normalized["caseResults"][1]["nistResult"] is failed


def test_normalizer_supplies_reason_when_nist_reason_is_missing() -> None:
    normalized = normalize_nist_validation(
        {"tests": [{"tgId": 1, "tcId": 1, "result": "error"}]}
    )
    assert normalized["failures"][0]["reason"] == "error"
    assert normalized["failures"][0]["provided"] == "error"


def test_normalizer_treats_malformed_tests_field_as_empty() -> None:
    validation = {"vsId": 7, "disposition": "failed", "tests": {"tcId": 1}}
    normalized = normalize_nist_validation(validation)
    assert normalized["summary"]["total"] == 0
    assert normalized["caseResults"] == []
    assert normalized["failures"] == []
    assert normalized["nistValidation"] is validation
