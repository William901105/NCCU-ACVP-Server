from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import pytest

from app.acvp_mldsa.expected import generate_expected_results_from_prompt
from app.acvp_protocol import service
from app.acvp_protocol.capabilities import (
    negotiate_mldsa_capabilities,
    validate_registration_container,
)
from app.acvp_protocol.vector_generation import (
    NIST_CONFORMANCE_PROFILE,
    generate_vector_sets_from_negotiated_capabilities,
)
from app.genval import GenValArtifacts, GenValSettings


CONFORMANCE_CAMPAIGN_SEED = (
    "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"
)


@pytest.fixture(autouse=True)
def fake_nist_genval_for_conformance_tests(monkeypatch: Any, tmp_path: Path) -> None:
    source_dir = tmp_path / "third_party" / "nist-acvp-server"
    source_dir.mkdir(parents=True)
    (source_dir / "NIST_SOURCE.md").write_text(
        "- source git commit: test-nist-genval\n",
        encoding="utf-8",
    )
    settings = GenValSettings(
        project_root=tmp_path,
        runner_dll=tmp_path / "runner.dll",
        artifact_root=tmp_path / "artifacts",
        timeout_seconds=5,
    )

    class FakeNistCliGenValProvider:
        def __init__(self, provider_settings: GenValSettings) -> None:
            self.settings = provider_settings

        def check_registration(
            self,
            registration: Dict[str, Any],
            work_dir: Path,
        ) -> Dict[str, Any]:
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "check.stdout.txt").write_text("", encoding="utf-8")
            (work_dir / "check.stderr.txt").write_text("", encoding="utf-8")
            return {"status": "passed"}

        def generate(
            self,
            registration: Dict[str, Any],
            work_dir: Path,
        ) -> GenValArtifacts:
            work_dir.mkdir(parents=True, exist_ok=True)
            prompt = _prompt_from_nist_registration(registration)
            expected = generate_expected_results_from_prompt(prompt)
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

        def validate(
            self,
            internal_projection: Path,
            response: Path,
            work_dir: Path,
        ) -> Path:
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


def _prompt_from_nist_registration(registration: Dict[str, Any]) -> Dict[str, Any]:
    local_registration = _local_registration_from_nist_registration(registration)
    negotiated = negotiate_mldsa_capabilities(
        validate_registration_container({"algorithms": [local_registration]})
    )
    prompt = generate_vector_sets_from_negotiated_capabilities(
        negotiated,
        campaign_seed=CONFORMANCE_CAMPAIGN_SEED,
        generation_profile=NIST_CONFORMANCE_PROFILE,
        tests_per_group=1,
    )[0]
    prompt["vsId"] = registration["vsId"]
    prompt["isSample"] = bool(registration.get("isSample", False))
    return prompt


def _local_registration_from_nist_registration(
    registration: Dict[str, Any],
) -> Dict[str, Any]:
    mode = registration["mode"]
    local_registration: Dict[str, Any] = {
        "algorithm": "ML-DSA",
        "mode": mode,
        "revision": "FIPS204",
        "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
    }
    if mode == "keyGen":
        local_registration["parameterSets"] = list(registration["parameterSets"])
        return local_registration

    signature_interfaces = list(registration["signatureInterfaces"])
    local_registration["signatureInterfaces"] = signature_interfaces
    local_registration["capabilities"] = list(registration["capabilities"])
    if mode == "sigGen":
        local_registration["deterministic"] = list(registration["deterministic"])
    if "internal" in signature_interfaces:
        local_registration["externalMu"] = list(registration.get("externalMu", [False]))
    if "external" in signature_interfaces:
        local_registration["preHash"] = list(registration.get("preHash", ["pure"]))
    return local_registration


def _validation_from_expected_response(
    expected: Dict[str, Any],
    received: Dict[str, Any],
) -> Dict[str, Any]:
    received_map = {
        (tg_id, tc_id): test
        for tg_id, tc_id, test in _tests_by_group(received)
    }
    tests = []
    for tg_id, tc_id, expected_test in _tests_by_group(expected):
        result = "passed" if received_map.get((tg_id, tc_id)) == expected_test else "failed"
        test_result = {"tgId": tg_id, "tcId": tc_id, "result": result}
        if result != "passed":
            test_result["reason"] = "response did not match expected result"
        tests.append(test_result)
    disposition = "passed" if all(test["result"] == "passed" for test in tests) else "failed"
    return {
        "vsId": expected["vsId"],
        "disposition": disposition,
        "tests": tests,
    }


def _tests_by_group(payload: Dict[str, Any]) -> Iterable[Tuple[Any, Any, Dict[str, Any]]]:
    for group in payload.get("testGroups", []):
        tg_id = group.get("tgId")
        for test in group.get("tests", []):
            yield tg_id, test.get("tcId"), test
