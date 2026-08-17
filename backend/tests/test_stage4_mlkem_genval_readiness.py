from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "nist" / "mlkem"
COPY_SCRIPT = REPO_ROOT / "scripts" / "nist" / "copy_nist_genval.sh"
STRICT_BASE_COMMIT = "2a351bc189cecafaecaa96bf1cfd91234d42d7b0"
CAPTURE_FEATURE_COMMIT = "531cc733a1bdfebe49063c0d0717116f19376a4a"
NIST_SOURCE_COMMIT = "15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0"
REFERENCE_COMMIT = "61b549e51ca18c75c303cf83f6fb58f40c1de700"
PARAMETER_SETS = {"ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"}
FORBIDDEN_PATH_TOKENS = ("/root/", "/home/", "/Users/", "C:\\", "D:\\", "/tmp/nccu-acvp-stage4")
FORBIDDEN_ORLEANS_TOKENS = (
    "failed initializing orleans client connection",
    "system.timeoutexception",
    "response did not arrive on time",
    "dashboard address already in use",
    "address already in use",
    "failed to bind",
    "bind failed",
    "unhandled exception",
    "fatal exception",
    "connection refused",
    "orleans client initialization failed",
)

CASES = {
    "keyGen": {
        "mode": "keyGen",
        "isSample": True,
        "functions": set(),
    },
    "encapDecap": {
        "mode": "encapDecap",
        "isSample": True,
        "functions": {
            "encapsulation",
            "decapsulation",
            "encapsulationKeyCheck",
            "decapsulationKeyCheck",
        },
    },
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_mlkem_registration_inputs_cover_the_stage4_matrix() -> None:
    for fixture_name, expected in CASES.items():
        registration = _read_json(FIXTURE_ROOT / fixture_name / "registration.json")

        assert registration["algorithm"] == "ML-KEM"
        assert registration["mode"] == expected["mode"]
        assert registration["revision"] == "FIPS203"
        assert registration["isSample"] is expected["isSample"]
        assert set(registration["parameterSets"]) == PARAMETER_SETS
        assert set(registration.get("functions", [])) == expected["functions"]


def test_mlkem_generated_artifacts_retain_identity_and_group_coverage() -> None:
    for fixture_name, expected in CASES.items():
        fixture_root = FIXTURE_ROOT / fixture_name
        artifacts = {
            name: _read_json(fixture_root / f"{name}.json")
            for name in ("prompt", "internalProjection", "expectedResults")
        }

        for payload in artifacts.values():
            assert payload["algorithm"] == "ML-KEM"
            assert payload["mode"] == expected["mode"]
            assert payload["revision"] == "FIPS203"
            assert payload["isSample"] is True
            assert payload["testGroups"]
            for group in payload["testGroups"]:
                assert isinstance(group["tgId"], int)
                assert group["tests"]
                assert all(isinstance(test["tcId"], int) for test in group["tests"])

        prompt_groups = artifacts["prompt"]["testGroups"]
        projection_groups = artifacts["internalProjection"]["testGroups"]
        assert {group["parameterSet"] for group in prompt_groups} == PARAMETER_SETS
        assert {group["parameterSet"] for group in projection_groups} == PARAMETER_SETS
        assert len(artifacts["expectedResults"]["testGroups"]) == len(prompt_groups)

        expected_functions = expected["functions"]
        assert {group.get("function") for group in prompt_groups if "function" in group} == expected_functions
        assert {
            group.get("function") for group in projection_groups if "function" in group
        } == expected_functions

        if expected["mode"] == "keyGen":
            assert all(
                {"d", "z"} <= set(test)
                for group in prompt_groups
                for test in group["tests"]
            )
        else:
            test_fields = {
                group["function"]: set(group["tests"][0])
                for group in prompt_groups
            }
            assert {"ek", "m"} <= test_fields["encapsulation"]
            assert {"dk", "c"} <= test_fields["decapsulation"]
            assert {"ek"} <= test_fields["encapsulationKeyCheck"]
            assert {"dk"} <= test_fields["decapsulationKeyCheck"]


def test_mlkem_capture_logs_record_successful_nist_check_and_generate() -> None:
    for fixture_name, expected in CASES.items():
        fixture_root = FIXTURE_ROOT / fixture_name
        nist_mode = expected["mode"][:1].upper() + expected["mode"][1:]

        for phase in ("check", "generate"):
            stdout = (fixture_root / f"{phase}.stdout.txt").read_text(encoding="utf-8")
            stderr = (fixture_root / f"{phase}.stderr.txt").read_text(encoding="utf-8")

            assert (fixture_root / f"{phase}.exitcode.txt").read_text(encoding="utf-8") == "0\n"
            assert f"Running in {phase.title()} mode for ML-KEM-{nist_mode}-FIPS203" in stdout
            assert stderr == ""
            combined_log = f"{stdout}\n{stderr}".lower()
            for token in FORBIDDEN_ORLEANS_TOKENS:
                assert token not in combined_log, (
                    "Stage 4 evidence contains forbidden runtime failure token "
                    f"{token!r}: {fixture_name}/{phase}"
                )


def test_mlkem_manifests_pin_source_provenance_and_artifact_hashes() -> None:
    for fixture_name, expected in CASES.items():
        fixture_root = FIXTURE_ROOT / fixture_name
        manifest = _read_json(fixture_root / "manifest.json")

        assert manifest["stage"] == 4
        assert manifest["stageName"] == "mlkem-genval-readiness"
        assert manifest["strictBaseCommit"] == STRICT_BASE_COMMIT
        assert manifest["stage4FeatureCommit"] == CAPTURE_FEATURE_COMMIT
        assert manifest["nistSourceCommit"] == NIST_SOURCE_COMMIT
        assert manifest["reference203Commit"] == REFERENCE_COMMIT
        assert manifest["dotnetVersion"] == "8.0.422"
        assert manifest["referenceSource"] == {
            "repository": "https://github.com/hhhylaiii/ACVP-Server",
            "commit": REFERENCE_COMMIT,
        }
        assert manifest["algorithm"] == "ML-KEM"
        assert manifest["mode"] == expected["mode"]
        assert manifest["revision"] == "FIPS203"
        assert manifest["isSample"] is True
        assert manifest["exitCodes"] == {"check": 0, "generate": 0}
        assert manifest["checkExitCode"] == 0
        assert manifest["generateExitCode"] == 0
        assert manifest["artifacts"] == {
            "prompt": "prompt.json",
            "internalProjection": "internalProjection.json",
            "expectedResults": "expectedResults.json",
        }
        assert set(manifest["files"]) == {
            path.name
            for path in fixture_root.iterdir()
            if path.name != "manifest.json" and path.suffix != ".log"
        }

        for relative_path, expected_hash in manifest["files"].items():
            artifact = fixture_root / relative_path
            assert artifact.is_file(), artifact
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_hash


def test_mlkem_tracked_text_evidence_has_no_machine_paths_or_temp_paths() -> None:
    for fixture_root in (FIXTURE_ROOT / "keyGen", FIXTURE_ROOT / "encapDecap"):
        evidence_files = [
            *fixture_root.glob("*.stdout.txt"),
            *fixture_root.glob("*.stderr.txt"),
            fixture_root / "manifest.json",
            fixture_root / "registration.json",
        ]
        for path in evidence_files:
            text = path.read_text(encoding="utf-8")
            assert all(token not in text for token in FORBIDDEN_PATH_TOKENS), path


def test_copy_script_requires_all_supported_fixture_directories() -> None:
    source = COPY_SCRIPT.read_text(encoding="utf-8")

    for name in (
        "ML-DSA-keyGen-FIPS204",
        "ML-DSA-sigGen-FIPS204",
        "ML-DSA-sigGen-FIPS204-tr1",
        "ML-DSA-sigVer-FIPS204",
        "ML-KEM-keyGen-FIPS203",
        "ML-KEM-encapDecap-FIPS203",
    ):
        assert name in source
    assert "Required NIST GenVal json-files directory is missing: ${name}" in source
    assert 'source_commit}" != "${PINNED_COMMIT}' in source
