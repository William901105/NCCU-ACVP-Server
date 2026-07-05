from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.acvp_mldsa.expected import generate_expected_results_from_prompt
from app.acvp_protocol import service
from app.acvp_protocol.service import ACVP_SKELETON_VECTOR_SET_STORE
from app.acvp_protocol.workflow_profile import STRICT_WORKFLOW_PROFILE
from app.genval import GenValArtifacts, GenValSettings
from app.models import AcvpV1TestSessionCreateRequest


def setup_function() -> None:
    service.ACVP_SKELETON_SESSION_STORE.clear()
    service.ACVP_SKELETON_VECTOR_SET_STORE.clear()


def test_strict_auto_generation_uses_nist_genval(monkeypatch: Any, tmp_path: Path) -> None:
    source_dir = tmp_path / "third_party" / "nist-acvp-server"
    source_dir.mkdir(parents=True)
    (source_dir / "NIST_SOURCE.md").write_text(
        "- source git commit: abc123\n",
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
            prompt = {
                "vsId": registration["vsId"],
                "algorithm": "ML-DSA",
                "mode": "keyGen",
                "revision": "FIPS204",
                "isSample": registration["isSample"],
                "testGroups": [
                    {
                        "tgId": 1,
                        "testType": "AFT",
                        "parameterSet": "ML-DSA-44",
                        "tests": [
                            {
                                "tcId": 1,
                                "seed": "00" * 32,
                            }
                        ],
                    }
                ],
            }
            expected = generate_expected_results_from_prompt(prompt)
            registration_path = work_dir / "registration.json"
            prompt_path = work_dir / "prompt.json"
            projection_path = work_dir / "internalProjection.json"
            expected_path = work_dir / "expectedResults.json"
            for path, payload in (
                (registration_path, registration),
                (prompt_path, prompt),
                (projection_path, {"vsId": registration["vsId"]}),
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

    monkeypatch.setattr(service, "get_genval_settings", lambda: settings)
    monkeypatch.setattr(service, "NistCliGenValProvider", FakeNistCliGenValProvider)

    response = service.create_test_session(
        AcvpV1TestSessionCreateRequest(
            algorithms=[
                {
                    "algorithm": "ML-DSA",
                    "mode": "keyGen",
                    "revision": "FIPS204",
                    "prereqVals": [{"algorithm": "SHA", "valValue": "same"}],
                    "parameterSets": ["ML-DSA-44"],
                }
            ]
        ),
        workflow_profile=STRICT_WORKFLOW_PROFILE,
    )

    assert response["generationProfile"] == "nist-conformance"
    assert response["vectorGeneration"]["provider"] == "nist-genval"
    assert response["vectorGeneration"]["localSkeletonBehavior"] is False
    assert response["vectorGeneration"]["hasInternalProjection"] is True
    assert response["vectorGeneration"]["expectedResultsDebugOnly"] is True

    vector_set = ACVP_SKELETON_VECTOR_SET_STORE[response["vectorSetIds"][0]]
    assert vector_set["provider"] == "nist-genval"
    assert vector_set["providerName"] == "NIST ACVP-Server GenValAppRunner"
    assert vector_set["nistSourceCommit"] == "abc123"
    assert vector_set["artifactPaths"]["internalProjection"].endswith("internalProjection.json")
    assert vector_set["expectedResultsDebugOnly"] is True
