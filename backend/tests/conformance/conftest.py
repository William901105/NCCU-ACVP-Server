from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import pytest

from app.acvp_protocol import service
from app.genval import GenValArtifacts, GenValSettings


FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "nist" / "mldsa"


@pytest.fixture(autouse=True)
def fake_nist_genval_for_conformance_tests(monkeypatch: Any, tmp_path: Path) -> None:
    source_dir = tmp_path / "third_party" / "nist-acvp-server"
    source_dir.mkdir(parents=True)
    (source_dir / "NIST_SOURCE.md").write_text("- source git commit: test-nist-genval\n", encoding="utf-8")
    settings = GenValSettings(
        project_root=tmp_path,
        runner_dll=tmp_path / "runner.dll",
        artifact_root=tmp_path / "artifacts",
        timeout_seconds=5,
    )

    class FakeNistCliGenValProvider:
        def __init__(self, provider_settings: GenValSettings) -> None:
            self.settings = provider_settings

        def check_registration(self, registration: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "check.stdout.txt").write_text("", encoding="utf-8")
            (work_dir / "check.stderr.txt").write_text("", encoding="utf-8")
            return {"status": "passed"}

        def generate(self, registration: Dict[str, Any], work_dir: Path) -> GenValArtifacts:
            work_dir.mkdir(parents=True, exist_ok=True)
            mode = str(registration["mode"])
            prompt = _fixture_payload(mode, "prompt.json")
            expected = _fixture_payload(mode, "expectedResults.json")
            prompt["vsId"] = registration["vsId"]
            expected["vsId"] = registration["vsId"]
            prompt["isSample"] = bool(registration.get("isSample", False))
            expected["isSample"] = bool(registration.get("isSample", False))
            registration_path = work_dir / "registration.json"
            prompt_path = work_dir / "prompt.json"
            projection_path = work_dir / "internalProjection.json"
            expected_path = work_dir / "expectedResults.json"
            for path, payload in (
                (registration_path, registration),
                (prompt_path, prompt),
                (projection_path, {"vsId": prompt["vsId"], "expectedResults": expected}),
                (expected_path, expected),
            ):
                service._write_json_file(path, payload)
            (work_dir / "generation.stdout.txt").write_text("", encoding="utf-8")
            (work_dir / "generation.stderr.txt").write_text("", encoding="utf-8")
            return GenValArtifacts(
                registration=registration_path,
                prompt=prompt_path,
                internal_projection=projection_path,
                expected_results=expected_path,
                stdout=work_dir / "generation.stdout.txt",
                stderr=work_dir / "generation.stderr.txt",
            )

        def validate(self, internal_projection: Path, response: Path, work_dir: Path) -> Path:
            projection = json.loads(internal_projection.read_text(encoding="utf-8"))
            expected = projection["expectedResults"]
            received = json.loads(response.read_text(encoding="utf-8"))
            validation = _validation_from_expected_response(expected, received)
            validation_path = work_dir / "validation.json"
            service._write_json_file(validation_path, validation)
            (work_dir / "validation.stdout.txt").write_text("", encoding="utf-8")
            (work_dir / "validation.stderr.txt").write_text("", encoding="utf-8")
            return validation_path

    monkeypatch.setattr(service, "get_genval_settings", lambda: settings)
    monkeypatch.setattr(service, "NistCliGenValProvider", FakeNistCliGenValProvider)


def _fixture_payload(mode: str, filename: str) -> Dict[str, Any]:
    return deepcopy(json.loads((FIXTURE_ROOT / mode / filename).read_text(encoding="utf-8")))


def _validation_from_expected_response(expected: Dict[str, Any], received: Dict[str, Any]) -> Dict[str, Any]:
    received_map = {(tg_id, tc_id): test for tg_id, tc_id, test in _tests_by_group(received)}
    tests = []
    for tg_id, tc_id, expected_test in _tests_by_group(expected):
        result = "passed" if received_map.get((tg_id, tc_id)) == expected_test else "failed"
        entry: Dict[str, Any] = {"tgId": tg_id, "tcId": tc_id, "result": result}
        if result == "failed":
            entry["reason"] = "response did not match NIST expected result"
        tests.append(entry)
    return {
        "vsId": expected["vsId"],
        "disposition": "passed" if all(test["result"] == "passed" for test in tests) else "failed",
        "tests": tests,
    }


def _tests_by_group(payload: Dict[str, Any]) -> Iterable[Tuple[Any, Any, Dict[str, Any]]]:
    for group in payload.get("testGroups", []):
        for test in group.get("tests", []):
            yield group.get("tgId"), test.get("tcId"), test
