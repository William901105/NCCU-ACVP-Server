from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List
from uuid import uuid4


REPORT_SCHEMA_VERSION = "1.0"
REPORT_ARTIFACT_TYPE = "acvp-validation-report"
REPORT_DISCLAIMER = (
    "This report records validation performed by the local NCCU ACVP Server. "
    "It is not a NIST/CAVP validation certificate."
)


def append_report_artifact(
    *,
    vector_set: Dict[str, Any],
    validation_result: Dict[str, Any],
    acvp_results: Dict[str, Any],
    response: Dict[str, Any],
) -> Dict[str, Any]:
    artifact = build_report_artifact(
        vector_set=vector_set,
        validation_result=validation_result,
        acvp_results=acvp_results,
        response=response,
    )

    existing = vector_set.get("report")
    artifacts: List[Dict[str, Any]] = []

    if isinstance(existing, dict):
        stored = existing.get("artifacts")
        if isinstance(stored, list):
            artifacts = [
                copy.deepcopy(item)
                for item in stored
                if isinstance(item, dict)
            ]
        elif existing.get("reportId"):
            artifacts = [copy.deepcopy(existing)]

    artifacts.append(artifact)

    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "artifactType": REPORT_ARTIFACT_TYPE,
        "latestReportId": artifact["reportId"],
        "artifacts": artifacts,
    }


def build_report_artifact(
    *,
    vector_set: Dict[str, Any],
    validation_result: Dict[str, Any],
    acvp_results: Dict[str, Any],
    response: Dict[str, Any],
) -> Dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    session_id = str(vector_set.get("testSessionId", "unknown"))
    vs_id = vector_set.get("vsId")
    disposition = (
        acvp_results.get("results", {}).get("disposition", "error")
        if isinstance(acvp_results, dict)
        else "error"
    )

    prompt = vector_set.get("prompt")
    prompt = prompt if isinstance(prompt, dict) else {}

    artifact: Dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "artifactType": REPORT_ARTIFACT_TYPE,
        "reportId": (
            f"NCCU-ACVP-REPORT-{session_id}-VS{vs_id}-"
            f"{uuid4().hex[:12]}"
        ),
        "generatedAt": generated_at,
        "testSessionId": session_id,
        "vsId": vs_id,
        "algorithm": vector_set.get("algorithm", prompt.get("algorithm")),
        "revision": vector_set.get("revision", prompt.get("revision")),
        "mode": vector_set.get("mode", prompt.get("mode")),
        "status": vector_set.get("status"),
        "disposition": disposition,
        "passed": disposition == "passed",
        "publishable": disposition == "passed",
        "validatedAt": vector_set.get("validatedAt"),
        "summary": _summary(validation_result),
        "testGroups": _test_groups(vector_set, validation_result),
        "responseSha256": _sha256_json(response),
        "disclaimer": REPORT_DISCLAIMER,
    }
    artifact["artifactSha256"] = _sha256_json(artifact)
    return artifact


def _summary(validation_result: Dict[str, Any]) -> Dict[str, int]:
    source = validation_result.get("summary")
    source = source if isinstance(source, dict) else {}

    return {
        key: _safe_int(source.get(key))
        for key in (
            "total",
            "passed",
            "failed",
            "missing",
            "malformed",
            "extra",
        )
    }


def _test_groups(
    vector_set: Dict[str, Any],
    validation_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    prompt = vector_set.get("prompt")
    groups = prompt.get("testGroups", []) if isinstance(prompt, dict) else []
    failures_by_tg: Dict[Any, List[Dict[str, Any]]] = {}

    case_results = validation_result.get("caseResults", [])
    for case in case_results if isinstance(case_results, list) else []:
        if not isinstance(case, dict) or case.get("status") == "passed":
            continue

        tg_id = case.get("tgId")
        failures_by_tg.setdefault(tg_id, []).append(
            {
                "tcId": case.get("tcId"),
                "status": str(case.get("status", "failed")),
                "reasons": _failure_reasons(case),
            }
        )

    artifacts: List[Dict[str, Any]] = []
    known_tg_ids = set()

    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue

        tg_id = group.get("tgId")
        known_tg_ids.add(tg_id)
        artifacts.append(
            {
                "tgId": tg_id,
                "configuration": {
                    key: copy.deepcopy(value)
                    for key, value in group.items()
                    if key not in {"tgId", "tests"}
                },
                "failedTests": failures_by_tg.get(tg_id, []),
            }
        )

    for tg_id, failed_tests in failures_by_tg.items():
        if tg_id not in known_tg_ids:
            artifacts.append(
                {
                    "tgId": tg_id,
                    "configuration": {},
                    "failedTests": failed_tests,
                }
            )

    return artifacts


def _failure_reasons(case: Dict[str, Any]) -> List[str]:
    failures = case.get("failures")
    reasons = [
        str(item["reason"])
        for item in failures
        if isinstance(item, dict) and item.get("reason")
    ] if isinstance(failures, list) else []

    return reasons or [str(case.get("status", "local validation failed"))]


def _safe_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
