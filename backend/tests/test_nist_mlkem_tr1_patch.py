from __future__ import annotations

import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_SHA256 = "d421d216a21d0ea38a596342dee6a4144598f33fd40b7b58d4a5916203573ade"
PATCH = (
    REPO_ROOT
    / "scripts"
    / "nist"
    / "patches"
    / "a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch"
)
VENDOR = REPO_ROOT / "third_party" / "nist-acvp-server"
GENERATOR = (
    VENDOR
    / "gen-val"
    / "src"
    / "generation"
    / "src"
    / "NIST.CVP.ACVTS.Libraries.Generation"
    / "ML-KEM"
    / "FIPS203"
    / "tr1"
    / "EncapDecap"
    / "TestGroupGeneratorKeyCheckVal.cs"
)
METADATA_TEST = (
    VENDOR
    / "gen-val"
    / "src"
    / "generation"
    / "test"
    / "NIST.CVP.ACVTS.Libraries.Generation.Tests"
    / "ML-KEM"
    / "FIPS203"
    / "tr1"
    / "EncapDecap"
    / "TestGroupGeneratorKeyCheckValTests.cs"
)


def test_local_nist_patch_hash_and_provenance_are_exact() -> None:
    assert hashlib.sha256(PATCH.read_bytes()).hexdigest() == PATCH_SHA256
    manifest = (VENDOR / "NIST_SOURCE.md").read_text(encoding="utf-8")
    patches = (VENDOR / "NIST_PATCHES.md").read_text(encoding="utf-8")
    assert "a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324" in manifest
    assert f"local patch sha256: {PATCH_SHA256}" in manifest
    assert "This is not an unmodified official NIST GenVal source tree." in manifest
    assert PATCH_SHA256 in patches
    assert "KeyFormat = PrivateKeyFormat.Expanded" in patches


def test_vendored_generator_and_metadata_regression_test_include_fix() -> None:
    generator = GENERATOR.read_text(encoding="utf-8-sig")
    metadata_test = METADATA_TEST.read_text(encoding="utf-8-sig")
    assert "using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.Enums;" in generator
    assert "KeyFormat = PrivateKeyFormat.Expanded," in generator
    assert "ShouldUseExpandedKeyFormatForDecapsulationKeyCheck" in metadata_test
    assert "Is.EqualTo(PrivateKeyFormat.Expanded)" in metadata_test


def test_copy_and_build_scripts_enforce_patch_identity() -> None:
    copy_script = (REPO_ROOT / "scripts" / "nist" / "copy_nist_genval.sh").read_text()
    build_script = (REPO_ROOT / "scripts" / "nist" / "build_nist_genval.sh").read_text()
    for source in (copy_script, build_script):
        assert PATCH_SHA256 in source
        assert "a7f283cd-mlkem-tr1-decap-keycheck-keyformat.patch" in source
    assert "apply --check" in copy_script
    assert "KeyFormat = PrivateKeyFormat\\.Expanded" in build_script
