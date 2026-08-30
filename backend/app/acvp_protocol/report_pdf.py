from __future__ import annotations

import textwrap
from typing import Any, Dict, Iterable, List


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 36
BODY_FONT_SIZE = 7
BODY_LEADING = 9
MAX_BODY_LINES = 78
MAX_TEXT_COLUMNS = 112


def render_validation_report_pdf(report: Dict[str, Any]) -> bytes:
    """Render a dependency-free, searchable, multi-page PDF report."""
    title = "NCCU ACVP Validation Report"
    session_id = str(report.get("testSessionId", "unknown"))
    body_lines = _report_lines(report)
    pages = [
        body_lines[index : index + MAX_BODY_LINES]
        for index in range(0, len(body_lines), MAX_BODY_LINES)
    ] or [[]]
    return _build_pdf(title=title, session_id=session_id, pages=pages)


def _report_lines(report: Dict[str, Any]) -> List[str]:
    session = _mapping(report.get("session"))
    summary = _mapping(report.get("summary"))
    certification = _mapping(report.get("certificationRequest"))
    request = _mapping(certification.get("request"))
    request_payload = _mapping(certification.get("requestPayload"))
    lines = [
        "REPORT INFORMATION",
        f"Report ID: {report.get('reportId', '-')}",
        f"Generated at: {report.get('generatedAt', '-')}",
        f"Test session ID: {report.get('testSessionId', '-')}",
        f"Session label: {_display(session.get('label'))}",
        f"Session status: {_display(session.get('status'))}",
        f"Overall result: {'PASSED' if summary.get('sessionPassed') else 'FAILED'}",
        f"Workflow policy: {_display(session.get('workflowPolicy'))}",
        f"Execution backend: {_display(session.get('executionBackend'))}",
        f"Created at: {_display(session.get('createdAt'))}",
        f"Last updated at: {_display(session.get('updatedAt'))}",
        "",
        "VALIDATION SUMMARY",
        (
            "Vector sets: "
            f"{summary.get('totalVectorSets', 0)} total, "
            f"{summary.get('passedVectorSets', 0)} passed, "
            f"{summary.get('failedVectorSets', 0)} failed"
        ),
        f"Downloaded vector sets: {summary.get('downloadedVectorSets', 0)}",
        f"Submitted vector sets: {summary.get('submittedVectorSets', 0)}",
        f"Pending vector sets: {summary.get('pendingVectorSets', 0)}",
        "",
        "CERTIFICATION REQUEST",
    ]
    if certification:
        lines.extend(
            [
                f"Status: {_display(request.get('status'))}",
                f"Request URL: {_display(request.get('url'))}",
                f"Submitted at: {_display(certification.get('submittedAt'))}",
                f"Module URL: {_display(request_payload.get('moduleUrl'))}",
                f"Operational environment URL: {_display(request_payload.get('oeUrl'))}",
                f"Message: {_display(request.get('message'))}",
            ]
        )
    else:
        lines.append("Status: Not submitted")

    vector_sets = report.get("vectorSets")
    for index, raw_vector in enumerate(
        vector_sets if isinstance(vector_sets, list) else [],
        start=1,
    ):
        vector = _mapping(raw_vector)
        metadata = _mapping(vector.get("metadata"))
        prompt = _mapping(vector.get("prompt"))
        validation = _mapping(vector.get("validationResults"))
        results = _mapping(validation.get("results"))
        artifact = _mapping(vector.get("validationArtifact"))
        artifact_summary = _mapping(artifact.get("summary"))
        tests = results.get("tests")
        test_results = tests if isinstance(tests, list) else []
        passed_tests = sum(
            1 for test in test_results if _test_outcome(test) == "passed"
        )
        failed_tests = sum(
            1 for test in test_results if _test_outcome(test) in {"fail", "failed"}
        )
        total_tests = _integer_or_default(
            artifact_summary.get("total"),
            len(test_results),
        )
        if artifact_summary:
            passed_tests = _integer_or_default(
                artifact_summary.get("passed"),
                passed_tests,
            )
            failed_tests = _integer_or_default(
                artifact_summary.get("failed"),
                failed_tests,
            )
        parameter_sets, test_types = _group_values(prompt)

        lines.extend(
            [
                "",
                f"VECTOR SET {index}",
                f"vsId: {_display(metadata.get('vsId', prompt.get('vsId')))}",
                f"Algorithm: {_display(metadata.get('algorithm', prompt.get('algorithm')))}",
                f"Revision: {_display(metadata.get('revision', prompt.get('revision')))}",
                f"Mode: {_display(metadata.get('mode', prompt.get('mode')))}",
                f"Parameter sets: {', '.join(parameter_sets) if parameter_sets else '-'}",
                f"Test types: {', '.join(test_types) if test_types else '-'}",
                f"Status: {_display(metadata.get('status'))}",
                f"Disposition: {_display(results.get('disposition'))}",
                f"Test groups: {_display(metadata.get('testGroupCount'))}",
                f"Test cases: {total_tests}",
                f"Passed test cases: {passed_tests}",
                f"Failed test cases: {failed_tests}",
                f"Validated at: {_display(metadata.get('validatedAt'))}",
                f"Provider: {_display(metadata.get('providerName', metadata.get('provider')))}",
            ]
        )

    lines.extend(
        [
            "",
            "DISCLAIMER",
            str(report.get("disclaimer", "")),
        ]
    )
    return list(_wrap_lines(lines))


def _mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _display(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _integer_or_default(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _test_outcome(value: Any) -> str:
    test = _mapping(value)
    result = test.get("result")
    return result.strip().lower() if isinstance(result, str) else ""


def _group_values(prompt: Dict[str, Any]) -> tuple[List[str], List[str]]:
    groups = prompt.get("testGroups")
    parameter_sets = set()
    test_types = set()
    for raw_group in groups if isinstance(groups, list) else []:
        group = _mapping(raw_group)
        parameter_set = group.get("parameterSet")
        test_type = group.get("testType")
        if isinstance(parameter_set, str) and parameter_set:
            parameter_sets.add(parameter_set)
        if isinstance(test_type, str) and test_type:
            test_types.add(test_type)
    return sorted(parameter_sets), sorted(test_types)


def _wrap_lines(lines: Iterable[str]) -> Iterable[str]:
    for line in lines:
        ascii_line = line.encode("ascii", "backslashreplace").decode("ascii")
        if len(ascii_line) <= MAX_TEXT_COLUMNS:
            yield ascii_line
            continue
        wrapped = textwrap.wrap(
            ascii_line,
            width=MAX_TEXT_COLUMNS,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        yield from wrapped or [""]


def _build_pdf(*, title: str, session_id: str, pages: List[List[str]]) -> bytes:
    page_object_ids = [5 + index * 2 for index in range(len(pages))]
    objects: Dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Count {len(pages)} /Kids "
            f"[{' '.join(f'{object_id} 0 R' for object_id in page_object_ids)}] >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>",
    }

    for page_index, (page_id, lines) in enumerate(zip(page_object_ids, pages), start=1):
        content_id = page_id + 1
        content = _page_content(
            title=title,
            session_id=session_id,
            page_number=page_index,
            page_count=len(pages),
            lines=lines,
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"\nendstream"
        )

    max_object_id = max(objects)
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_object_id + 1)
    for object_id in range(1, max_object_id + 1):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {max_object_id + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _page_content(
    *,
    title: str,
    session_id: str,
    page_number: int,
    page_count: int,
    lines: List[str],
) -> bytes:
    commands = [
        "BT",
        "/F2 11 Tf",
        f"{MARGIN} {PAGE_HEIGHT - MARGIN - 4} Td",
        f"({_pdf_escape(title)}) Tj",
        "ET",
        "BT",
        "/F1 6 Tf",
        f"{MARGIN} {PAGE_HEIGHT - MARGIN - 18} Td",
        f"(Session {_pdf_escape(session_id)}) Tj",
        "ET",
        "BT",
        f"/F1 {BODY_FONT_SIZE} Tf",
        f"{BODY_LEADING} TL",
        f"{MARGIN} {PAGE_HEIGHT - MARGIN - 34} Td",
    ]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.extend(
        [
            "ET",
            "BT",
            "/F1 6 Tf",
            f"{PAGE_WIDTH - 112} 20 Td",
            f"(Page {page_number} of {page_count}) Tj",
            "ET",
        ]
    )
    return "\n".join(commands).encode("ascii")


def _pdf_escape(value: str) -> str:
    ascii_value = value.encode("ascii", "backslashreplace").decode("ascii")
    return ascii_value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
