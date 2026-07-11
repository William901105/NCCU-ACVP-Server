from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_report(import_id: str, validation_result: dict[str, Any]) -> dict[str, Any]:
    metadata = validation_result["metadata"]
    summary = validation_result["summary"]
    report = {
        "importId": import_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "algorithm": metadata.get("algorithm"),
        "mode": metadata.get("mode"),
        "revision": metadata.get("revision"),
        "vsId": metadata.get("vsId"),
        "totalTestCases": summary["total"],
        "passedCount": summary["passed"],
        "failedCount": summary["failed"],
        "missingCount": summary["missing"],
        "malformedCount": summary["malformed"],
        "extraCount": summary.get("extra", 0),
        "failureDetails": validation_result["failures"],
    }
    report["markdown"] = export_report_markdown(report)
    return report


def export_report_json(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "markdown"}


def export_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NCCU ACVP Server | FIPS 204 / ML-DSA Validation Report",
        "",
        f"- importId: `{report['importId']}`",
        f"- generatedAt: `{report['generatedAt']}`",
        f"- algorithm: `{report.get('algorithm')}`",
        f"- mode: `{report.get('mode')}`",
        f"- revision: `{report.get('revision')}`",
        f"- vsId: `{report.get('vsId')}`",
        "",
        "## Summary",
        "",
        "| total | passed | failed | missing | malformed | extra |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {report['totalTestCases']} | {report['passedCount']} | "
            f"{report['failedCount']} | {report['missingCount']} | "
            f"{report['malformedCount']} | {report['extraCount']} |"
        ),
        "",
        "## Failure Details",
        "",
    ]

    failures = report.get("failureDetails", [])
    if not failures:
        lines.append("No failures.")
        return "\n".join(lines)

    lines.extend(
        [
            "| tgId | tcId | field | reason | expected | provided |",
            "| ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for failure in failures:
        lines.append(
            "| {tgId} | {tcId} | {field} | {reason} | `{expected}` | `{provided}` |".format(
                tgId=failure.get("tgId"),
                tcId=failure.get("tcId"),
                field=_escape_cell(failure.get("field")),
                reason=_escape_cell(failure.get("reason")),
                expected=_escape_cell(failure.get("expected")),
                provided=_escape_cell(failure.get("provided")),
            )
        )
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")
