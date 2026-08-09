from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DLL = (
    REPO_ROOT
    / ".nist-bin"
    / "genval-runner"
    / "NIST.CVP.ACVTS.Generation.GenValApp.dll"
)
FIXTURES = (
    REPO_ROOT / "third_party" / "nist-acvp-server" / "gen-val" / "json-files"
)

pytestmark = pytest.mark.skipif(
    os.environ.get("NCCU_ACVP_LIVE_TR1") != "1",
    reason=(
        "set NCCU_ACVP_LIVE_TR1=1, start the patched pinned Orleans host, and provide "
        "DILITHIUM_PY_SRC/KYBER_PY_SRC to run real tr1 IUT acceptance"
    ),
)


def test_mldsa_tr1_real_generation_iut_validation_and_mutation(
    tmp_path: Path,
) -> None:
    registration = _fixture("ML-DSA-sigGen-FIPS204-tr1", "registration.json")
    case = _generate(registration, tmp_path / "mldsa")
    prompt = _load(case / "prompt.json")
    assert len(prompt["testGroups"]) == 48
    assert {group["keyFormat"] for group in prompt["testGroups"]} == {
        "expanded", "seed"
    }
    assert {
        (group["signatureInterface"], group["deterministic"])
        for group in prompt["testGroups"]
    } == {
        ("external", False), ("external", True),
        ("internal", False), ("internal", True),
    }
    actual_product = {
        (
            group["parameterSet"],
            group["keyFormat"],
            group["signatureInterface"],
            group["deterministic"],
            group.get("preHash") if group["signatureInterface"] == "external"
            else group.get("externalMu"),
        )
        for group in prompt["testGroups"]
    }
    expected_product = {
        (parameter_set, key_format, "external", deterministic, pre_hash)
        for parameter_set in ("ML-DSA-44", "ML-DSA-65", "ML-DSA-87")
        for key_format in ("expanded", "seed")
        for deterministic in (False, True)
        for pre_hash in ("pure", "preHash")
    } | {
        (parameter_set, key_format, "internal", deterministic, external_mu)
        for parameter_set in ("ML-DSA-44", "ML-DSA-65", "ML-DSA-87")
        for key_format in ("expanded", "seed")
        for deterministic in (False, True)
        for external_mu in (False, True)
    }
    assert actual_product == expected_product
    assert sum(len(group["tests"]) for group in prompt["testGroups"]) == 720

    _run_iut(
        "mldsa-native",
        case,
        "DILITHIUM_PY_SRC",
        "--dilithium-py-src",
    )
    _assert_nist_validation(case, "response_pass_sigGen.json", "passed")
    _assert_nist_validation(case, "response_fail_sigGen.json", "failed")


def test_mlkem_tr1_real_generation_iut_validation_and_mutation(
    tmp_path: Path,
) -> None:
    registration = {
        "vsId": 43,
        "algorithm": "ML-KEM",
        "mode": "encapDecap",
        "revision": "FIPS203-tr1",
        "isSample": False,
        "parameterSets": ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"],
        "functions": [
            "encapsulation", "decapsulation", "encapsulationKeyCheck",
            "decapsulationKeyCheck",
        ],
        "keyFormats": ["seed", "expanded"],
    }
    case = _generate(registration, tmp_path / "mlkem")
    prompt = _load(case / "prompt.json")
    assert len(prompt["testGroups"]) == 15
    assert sum(len(group["tests"]) for group in prompt["testGroups"]) == 195
    assert {group["function"] for group in prompt["testGroups"]} == {
        "encapsulation", "decapsulation", "encapsulationKeyCheck",
        "decapsulationKeyCheck",
    }
    decapsulation = [
        group for group in prompt["testGroups"]
        if group["function"] == "decapsulation"
    ]
    assert {group["keyFormat"] for group in decapsulation} == {
        "expanded", "seed"
    }
    decapsulation_key_checks = [
        group for group in prompt["testGroups"]
        if group["function"] == "decapsulationKeyCheck"
    ]
    assert {
        group["parameterSet"] for group in decapsulation_key_checks
    } == {"ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"}
    assert all(
        group["keyFormat"] == "expanded"
        for group in decapsulation_key_checks
    )
    assert all(
        set(test) == {"tcId", "dk"}
        for group in decapsulation_key_checks
        for test in group["tests"]
    )

    _run_iut("mlkem-native", case, "KYBER_PY_SRC", "--kyber-py-src")
    _assert_nist_validation(case, "response_pass_encapDecap.json", "passed")
    _write_function_mutation(
        case,
        prompt,
        function="decapsulation",
        field="k",
        output_name="response_fail_shared_key.json",
    )
    _assert_nist_validation(case, "response_fail_shared_key.json", "failed")
    _write_function_mutation(
        case,
        prompt,
        function="decapsulationKeyCheck",
        field="testPassed",
        output_name="response_fail_decap_key_check.json",
    )
    _assert_nist_validation(
        case, "response_fail_decap_key_check.json", "failed"
    )


@pytest.mark.parametrize(
    (
        "fixture_directory",
        "runner_directory",
        "source_env",
        "source_flag",
        "response_name",
        "expected_groups",
        "expected_tests",
    ),
    [
        (
            "ML-DSA-keyGen-FIPS204", "mldsa-native", "DILITHIUM_PY_SRC",
            "--dilithium-py-src", "response_pass_keyGen.json", 3, 75,
        ),
        (
            "ML-DSA-sigGen-FIPS204", "mldsa-native", "DILITHIUM_PY_SRC",
            "--dilithium-py-src", "response_pass_sigGen.json", 24, 360,
        ),
        (
            "ML-DSA-sigVer-FIPS204", "mldsa-native", "DILITHIUM_PY_SRC",
            "--dilithium-py-src", "response_pass_sigVer.json", 12, 180,
        ),
        (
            "ML-KEM-keyGen-FIPS203", "mlkem-native", "KYBER_PY_SRC",
            "--kyber-py-src", "response_pass_keyGen.json", 3, 75,
        ),
        (
            "ML-KEM-encapDecap-FIPS203", "mlkem-native", "KYBER_PY_SRC",
            "--kyber-py-src", "response_pass_encapDecap.json", 12, 165,
        ),
    ],
    ids=[
        "mldsa-keygen-fips204",
        "mldsa-siggen-fips204",
        "mldsa-sigver-fips204",
        "mlkem-keygen-fips203",
        "mlkem-encapdecap-fips203",
    ],
)
def test_legacy_identity_real_generation_iut_validation(
    tmp_path: Path,
    fixture_directory: str,
    runner_directory: str,
    source_env: str,
    source_flag: str,
    response_name: str,
    expected_groups: int,
    expected_tests: int,
) -> None:
    registration = _fixture(fixture_directory, "registration.json")
    case = _generate(registration, tmp_path / fixture_directory)
    prompt = _load(case / "prompt.json")
    assert len(prompt["testGroups"]) == expected_groups
    assert (
        sum(len(group["tests"]) for group in prompt["testGroups"])
        == expected_tests
    )
    _run_iut(runner_directory, case, source_env, source_flag)
    _assert_nist_validation(case, response_name, "passed")


def _generate(registration: Dict[str, Any], case: Path) -> Path:
    if not RUNNER_DLL.is_file():
        pytest.fail("pinned GenVal runner is not built")
    case.mkdir(parents=True)
    registration_path = case / "registration.json"
    registration_path.write_text(json.dumps(registration, indent=2) + "\n")
    _genval("-c", registration_path)
    _genval("-g", registration_path)
    for name in ("prompt.json", "internalProjection.json", "expectedResults.json"):
        assert (case / name).is_file()
    return case


def _run_iut(
    runner_dir: str,
    case: Path,
    source_env: str,
    source_flag: str,
) -> None:
    source = os.environ.get(source_env)
    if not source:
        pytest.fail(f"{source_env} is required for live IUT acceptance")
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "IUT-tests" / runner_dir / "run_test.py"),
            "--prompt", str(case / "prompt.json"),
            "--response-dir", str(case),
            "--variant", "both",
            source_flag, source,
        ],
        check=True,
    )


def _assert_nist_validation(
    case: Path, response_name: str, disposition: str
) -> None:
    result = _genval(
        "-n", case / "internalProjection.json", "-b", case / response_name,
        check=False,
    )
    validation = _load(case / "validation.json")
    assert validation["disposition"] == disposition
    assert result.returncode == (0 if disposition == "passed" else 13)


def _write_function_mutation(
    case: Path,
    prompt: Dict[str, Any],
    *,
    function: str,
    field: str,
    output_name: str,
) -> None:
    response = copy.deepcopy(_load(case / "response_pass_encapDecap.json"))
    function_by_group = {
        group["tgId"]: group["function"] for group in prompt["testGroups"]
    }
    group = next(
        group for group in response["testGroups"]
        if function_by_group[group["tgId"]] == function
    )
    test = group["tests"][0]
    if field == "testPassed":
        test[field] = not test[field]
    else:
        value = test[field]
        test[field] = ("0" if value[0].upper() != "0" else "1") + value[1:]
    (case / output_name).write_text(json.dumps(response, indent=2) + "\n")


def _genval(*arguments: Any, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["dotnet", str(RUNNER_DLL), *(str(item) for item in arguments)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        pytest.fail(result.stdout + result.stderr)
    return result


def _fixture(directory: str, name: str) -> Dict[str, Any]:
    return _load(FIXTURES / directory / name)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())
