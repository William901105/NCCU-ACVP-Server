from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from ..acvp_parser import extract_algorithm_metadata, normalize_acvp_json


def normalize_nist_validation(
    validation: Dict[str, Any],
    *,
    prompt: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    if prompt is not None:
        metadata.update(extract_algorithm_metadata(normalize_acvp_json(prompt)))
    metadata["vsId"] = validation.get("vsId", metadata.get("vsId"))
    metadata["provider"] = "nist-genval"
    metadata["validationDisposition"] = validation.get("disposition")

    tests = validation.get("tests", [])
    if not isinstance(tests, list):
        tests = []

    counts: Counter[str] = Counter()
    failures: List[Dict[str, Any]] = []
    case_results: List[Dict[str, Any]] = []

    for item in tests:
        if not isinstance(item, dict):
            continue
        result = str(item.get("result", "")).lower()
        status = "passed" if result == "passed" else "failed"
        counts[status] += 1
        tc_id = item.get("tcId")
        case_failures: List[Dict[str, Any]] = []
        if status != "passed":
            failure = {
                "tgId": item.get("tgId"),
                "tcId": tc_id,
                "field": "result",
                "reason": item.get("reason") or result or "NIST validation failed",
                "expected": "passed",
                "provided": item.get("result"),
            }
            failures.append(failure)
            case_failures.append(failure)
        case_results.append(
            {
                "tgId": item.get("tgId"),
                "tcId": tc_id,
                "status": status,
                "prompt": None,
                "expected": None,
                "response": None,
                "failures": case_failures,
                "group": None,
                "nistResult": item,
            }
        )

    summary = {
        "total": len(tests),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "missing": 0,
        "malformed": 0,
        "extra": 0,
    }
    return {
        "metadata": metadata,
        "summary": summary,
        "failures": failures,
        "caseResults": case_results,
        "nistValidation": validation,
    }
