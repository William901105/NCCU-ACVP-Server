from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.acvp_core.algorithm_identity import AlgorithmIdentity
from app.acvp_core.bootstrap import build_algorithm_registry
from app.acvp_core.schema_error import AcvpSchemaError
from app.acvp_protocol import service
from app.algorithms.mldsa.module import MldsaAlgorithmModule, MldsaTr1AlgorithmModule


REPO_ROOT = Path(__file__).resolve().parents[2]
NIST_FIXTURES = (
    REPO_ROOT / "third_party" / "nist-acvp-server" / "gen-val" / "json-files"
)


def _tr1_registration() -> dict:
    return {
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204-tr1",
        "deterministic": [True, False],
        "externalMu": [True, False],
        "keyFormats": ["seed", "expanded"],
        "signatureInterfaces": ["external", "internal"],
        "preHash": ["pure", "preHash"],
        "capabilities": [{
            "parameterSets": ["ML-DSA-44"],
            "messageLength": [{"min": 8, "max": 128, "increment": 8}],
            "contextLength": [{"min": 0, "max": 64, "increment": 8}],
            "hashAlgs": ["SHA2-256"],
        }],
    }


def test_registry_exposes_only_the_seven_official_identities() -> None:
    assert set(build_algorithm_registry().identities()) == {
        AlgorithmIdentity("ML-DSA", "keyGen", "FIPS204"),
        AlgorithmIdentity("ML-DSA", "sigGen", "FIPS204"),
        AlgorithmIdentity("ML-DSA", "sigVer", "FIPS204"),
        AlgorithmIdentity("ML-DSA", "sigGen", "FIPS204-tr1"),
        AlgorithmIdentity("ML-KEM", "keyGen", "FIPS203"),
        AlgorithmIdentity("ML-KEM", "encapDecap", "FIPS203"),
        AlgorithmIdentity("ML-KEM", "encapDecap", "FIPS203-tr1"),
    }


@pytest.mark.parametrize(
    "algorithm,mode,revision",
    [
        ("ML-DSA", "keyGen", "FIPS204-tr1"),
        ("ML-DSA", "sigVer", "FIPS204-tr1"),
        ("ML-KEM", "keyGen", "FIPS203-tr1"),
    ],
)
def test_registry_rejects_undefined_mode_revision_combinations(
    algorithm: str, mode: str, revision: str
) -> None:
    with pytest.raises(AcvpSchemaError) as exc:
        service._module_for_identity(
            build_algorithm_registry(), algorithm, mode, revision, "$"
        )
    assert exc.value.code == "unsupported_mode_revision_combination"
    assert exc.value.path == "$.revision"


def test_mldsa_tr1_registration_negotiation_and_mapping_preserve_revision() -> None:
    module = MldsaTr1AlgorithmModule()
    registration = module.validate_registration(_tr1_registration())
    negotiated = module.negotiate_capabilities(registration)
    mapped = module.to_nist_registration(registration, vs_id=91, is_sample=True)

    assert negotiated["revision"] == "FIPS204-tr1"
    assert negotiated["negotiated"][0]["keyFormats"] == ["expanded", "seed"]
    assert mapped["revision"] == "FIPS204-tr1"
    assert mapped["keyFormats"] == ["seed", "expanded"]


def test_mldsa_tr1_registration_requires_valid_key_formats() -> None:
    missing = _tr1_registration()
    missing.pop("keyFormats")
    with pytest.raises(AcvpSchemaError) as exc:
        MldsaTr1AlgorithmModule().validate_registration(missing)
    assert exc.value.path == "$.keyFormats"

    invalid = _tr1_registration()
    invalid["keyFormats"] = ["privateKey"]
    with pytest.raises(AcvpSchemaError) as exc:
        MldsaTr1AlgorithmModule().validate_registration(invalid)
    assert exc.value.code == "invalid_key_format"


def test_mldsa_legacy_rejects_tr1_key_formats() -> None:
    registration = _tr1_registration()
    registration["revision"] = "FIPS204"
    with pytest.raises(AcvpSchemaError) as exc:
        MldsaAlgorithmModule().validate_registration(registration)
    assert exc.value.code == "invalid_conditional_field"


def test_official_mldsa_tr1_fixture_validates_seed_and_expanded_groups() -> None:
    fixture_dir = NIST_FIXTURES / "ML-DSA-sigGen-FIPS204-tr1"
    prompt = json.loads((fixture_dir / "prompt.json").read_text())
    expected = json.loads((fixture_dir / "expectedResults.json").read_text())
    module = MldsaTr1AlgorithmModule()

    validated = module.validate_prompt(prompt)
    module.validate_response(expected, expected_mode="sigGen")
    formats = {group["keyFormat"] for group in validated["testGroups"]}
    assert formats == {"seed", "expanded"}
    for group in validated["testGroups"]:
        expected_field = "seed" if group["keyFormat"] == "seed" else "sk"
        assert all(expected_field in test for test in group["tests"])


@pytest.mark.parametrize(
    "runner,algorithm,mode,revision",
    [
        ("mldsa-native", "ML-DSA", "keyGen", "FIPS204-tr1"),
        ("mlkem-native", "ML-KEM", "keyGen", "FIPS203-tr1"),
    ],
)
def test_iut_rejects_unknown_revision_identity_before_loading_crypto(
    tmp_path: Path, runner: str, algorithm: str, mode: str, revision: str
) -> None:
    prompt = tmp_path / "prompt.json"
    prompt.write_text(json.dumps({
        "vsId": 1,
        "algorithm": algorithm,
        "mode": mode,
        "revision": revision,
        "testGroups": [],
    }))
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "IUT-tests" / runner / "run_test.py"),
            "--prompt", str(prompt),
            "--response-dir", str(tmp_path),
            "--variant", "pass",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unsupported" in result.stderr
    assert revision in result.stderr
