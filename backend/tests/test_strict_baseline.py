from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ROOT = REPO_ROOT / "docs" / "baseline"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "nist" / "mldsa"
MODES = ("keyGen", "sigGen", "sigVer")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_manifest_is_parseable_and_has_expected_metadata() -> None:
    manifest = _read_json(BASELINE_ROOT / "runtime-manifest.json")

    assert manifest["projectName"] == "NCCU-ACVP-Server"
    assert manifest["baselineBranch"] == "feat/nist-genval-adapter"
    assert manifest["baselineCommit"] == "a16afec310b6acb604193e18dab4ee57e9bc06d2"
    assert manifest["nistSourceCommit"] == "15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0"
    assert manifest["fixtureModes"] == list(MODES)
    assert manifest["genValRunner"].startswith(".nist-bin/")


def test_fixture_manifests_match_runtime_metadata_and_hashes() -> None:
    runtime = _read_json(BASELINE_ROOT / "runtime-manifest.json")

    for mode in MODES:
        mode_root = FIXTURE_ROOT / mode
        manifest = _read_json(mode_root / "manifest.json")

        assert manifest["mode"] == mode
        assert manifest["nistSourceCommit"] == runtime["nistSourceCommit"]
        assert manifest["baselineApplicationCommit"] == runtime["baselineCommit"]
        for relative_path, expected_hash in manifest["files"].items():
            path = mode_root / relative_path
            assert path.is_file(), path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash


def test_all_fixture_json_is_parseable_and_has_required_files() -> None:
    required = {
        "registration.json",
        "prompt.json",
        "internalProjection.json",
        "expectedResults.json",
        "response.pass.json",
        "response.fail.json",
        "validation.pass.json",
        "validation.fail.json",
        "manifest.json",
    }

    for mode in MODES:
        mode_root = FIXTURE_ROOT / mode
        assert required <= {path.name for path in mode_root.glob("*.json")}
        for path in mode_root.glob("*.json"):
            _read_json(path)


def test_fixture_protocol_metadata_and_validation_dispositions() -> None:
    for mode in MODES:
        mode_root = FIXTURE_ROOT / mode
        registration = _read_json(mode_root / "registration.json")
        prompt = _read_json(mode_root / "prompt.json")
        expected = _read_json(mode_root / "expectedResults.json")
        response_pass = _read_json(mode_root / "response.pass.json")
        response_fail = _read_json(mode_root / "response.fail.json")
        validation_pass = _read_json(mode_root / "validation.pass.json")
        validation_fail = _read_json(mode_root / "validation.fail.json")

        for payload in (registration, prompt, expected, response_pass, response_fail):
            assert payload["algorithm"] == "ML-DSA"
            assert payload["revision"] == "FIPS204"
        assert registration["mode"] == mode
        assert prompt["mode"] == mode
        assert expected["mode"] == mode
        assert response_pass["testGroups"] == expected["testGroups"]
        assert response_fail["testGroups"] != expected["testGroups"]
        assert validation_pass["disposition"] == "passed"
        assert validation_fail["disposition"] == "failed"


def test_baseline_snapshots_are_parseable_and_retain_legacy_surface() -> None:
    openapi = _read_json(BASELINE_ROOT / "openapi-pre-strict.json")
    assert "/acvp/v1/testSessions" in openapi["paths"]
    assert "/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results" in openapi["paths"]
    assert "/api/import" in openapi["paths"]
    assert "/api/demo/clear" in openapi["paths"]
    assert "/api/oracle/mldsa/keygen" in openapi["paths"]

    schema = (BASELINE_ROOT / "storage-schema-pre-strict.sql").read_text(encoding="utf-8")
    for table in ("imports", "demo_sessions", "acvp_sessions", "acvp_vector_sets", "state_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema


def test_project_metadata_uses_nccu_name_without_renaming_protocol_values() -> None:
    package = _read_json(REPO_ROOT / "frontend" / "package.json")
    package_lock = _read_json(REPO_ROOT / "frontend" / "package-lock.json")
    main_source = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    index_source = (REPO_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    registry_source = (REPO_ROOT / "frontend" / "src" / "registry.ts").read_text(encoding="utf-8")

    assert package["name"] == "nccu-acvp-server-frontend"
    assert package_lock["name"] == "nccu-acvp-server-frontend"
    assert package_lock["packages"][""].get("name") == "nccu-acvp-server-frontend"
    assert "NCCU ACVP Server" in main_source
    assert "NCCU ACVP Server" in index_source
    assert "ML-DSA" in registry_source
    assert "FIPS204" in registry_source
    assert "FIPS203" in registry_source


def test_fixtures_and_manifest_have_no_runtime_absolute_path() -> None:
    forbidden = str(REPO_ROOT)
    for path in FIXTURE_ROOT.rglob("*"):
        if path.is_file():
            assert forbidden not in path.read_text(encoding="utf-8", errors="replace")
