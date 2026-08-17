from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.acvp_core.algorithm_identity import AlgorithmIdentity
from app.acvp_core.bootstrap import build_algorithm_registry
from app.acvp_core.schema_error import AcvpSchemaError
from app.acvp_protocol.routes import get_acvp_v1_algorithms
from app.algorithms.mlkem import MlkemAlgorithmModule
from app.algorithms.mlkem.capabilities import negotiate_mlkem_capabilities


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_mlkem_descriptor_and_supported_identities() -> None:
    module = MlkemAlgorithmModule()
    descriptor = module.descriptor.to_dict()

    assert descriptor == {
        "providerId": "nist-ml-kem-fips203",
        "algorithm": "ML-KEM",
        "revision": "FIPS203",
        "displayName": "ML-KEM (FIPS 203)",
        "enabled": True,
        "modes": ["keyGen", "encapDecap"],
        "parameterSets": ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"],
        "registrationSchemaVersion": "draft-celi-acvp-ml-kem-01",
        "responseSchemaVersion": "draft-celi-acvp-ml-kem-01",
        "workflowPolicy": "strict",
        "executionBackend": "nist-genval",
        "nistReferences": [
            "https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html",
            "https://csrc.nist.gov/pubs/fips/203/final",
        ],
        "identities": [
            {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"},
            {
                "algorithm": "ML-KEM",
                "mode": "encapDecap",
                "revision": "FIPS203",
            },
        ],
        "functions": [
            "encapsulation",
            "decapsulation",
            "encapsulationKeyCheck",
            "decapsulationKeyCheck",
        ],
        "testTypes": {
            "keyGen": ["AFT"],
            "encapsulation": ["AFT"],
            "decapsulation": ["VAL"],
            "encapsulationKeyCheck": ["VAL"],
            "decapsulationKeyCheck": ["VAL"],
        },
    }
    assert module.supports(AlgorithmIdentity("ML-KEM", "keyGen", "FIPS203"))
    assert module.supports(AlgorithmIdentity("ML-KEM", "encapDecap", "FIPS203"))
    assert not module.supports(AlgorithmIdentity("ML-KEM", "keyGen", "FIPS204"))
    assert not module.supports(AlgorithmIdentity("ML-DSA", "keyGen", "FIPS203"))
    assert not module.supports(AlgorithmIdentity("ML-KEM", "sigGen", "FIPS203"))


def test_production_registry_contains_three_providers_and_six_identities() -> None:
    registry = build_algorithm_registry()
    descriptors = registry.list_descriptors()

    assert len(registry) == 3
    assert [item["providerId"] for item in descriptors] == [
        "nist-ml-dsa-fips204",
        "nist-ml-dsa-fips204-tr1",
        "nist-ml-kem-fips203",
    ]
    assert len(registry.identities()) == 6
    assert len({item["providerId"] for item in descriptors}) == 3
    mldsa = descriptors[0]
    assert mldsa["modes"] == ["keyGen", "sigGen", "sigVer"]
    assert mldsa["parameterSets"] == ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]


def test_algorithms_endpoint_emits_the_mlkem_descriptor() -> None:
    response = get_acvp_v1_algorithms(build_algorithm_registry())
    payload = response[1]
    mlkem = next(
        item for item in payload["algorithms"] if item["providerId"] == "nist-ml-kem-fips203"
    )
    assert mlkem["modes"] == ["keyGen", "encapDecap"]
    assert mlkem["revision"] == "FIPS203"


def test_mlkem_module_negotiation_preserves_client_order() -> None:
    result = MlkemAlgorithmModule().negotiate_capabilities(
        {
            "algorithm": "ML-KEM",
            "mode": "encapDecap",
            "revision": "FIPS203",
            "parameterSets": ["ML-KEM-1024", "ML-KEM-512"],
            "functions": ["decapsulation", "encapsulation"],
        }
    )

    assert result["algorithm"] == "ML-KEM"
    assert result["revision"] == "FIPS203"
    assert result["negotiated"] == [
        {
            "mode": "encapDecap",
            "parameterSets": ["ML-KEM-1024", "ML-KEM-512"],
            "functions": ["decapsulation", "encapsulation"],
            "status": "accepted",
        }
    ]
    assert result["unsupported"] == []
    assert result["warnings"] == []


def test_mlkem_negotiation_rejects_an_empty_capability_container() -> None:
    with pytest.raises(AcvpSchemaError) as exc_info:
        negotiate_mlkem_capabilities({"algorithms": []})
    assert exc_info.value.code == "UNSUPPORTED_CAPABILITIES"
    assert exc_info.value.path == "$.algorithms"


def test_mlkem_dependency_boundaries_and_bootstrap_composition_root() -> None:
    forbidden = ("algorithms.mldsa", "fastapi", "storage", "genval", "subprocess")
    violations = []
    for path in (APP_ROOT / "algorithms" / "mlkem").glob("*.py"):
        for imported in _imports(path):
            if any(token in imported for token in forbidden):
                violations.append(f"{path.name}: {imported}")
    assert violations == []

    concrete_importers = []
    for path in APP_ROOT.rglob("*.py"):
        imports = set(_imports(path))
        if any("algorithms.mldsa" in item for item in imports) and any(
            "algorithms.mlkem" in item for item in imports
        ):
            concrete_importers.append(path.relative_to(APP_ROOT).as_posix())
    assert concrete_importers == ["acvp_core/bootstrap.py"]


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""
