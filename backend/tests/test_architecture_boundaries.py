from __future__ import annotations

import ast
import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_algorithm_neutral_packages_do_not_import_mldsa() -> None:
    roots = ("acvp_core", "acvp_protocol", "genval", "storage")
    violations = []
    for root_name in roots:
        for path in (APP_ROOT / root_name).rglob("*.py"):
            if path == APP_ROOT / "acvp_core" / "bootstrap.py":
                continue
            for imported in _imports(path):
                if "algorithms.mldsa" in imported or "acvp_mldsa" in imported:
                    violations.append(f"{path.relative_to(APP_ROOT)}: {imported}")
    assert violations == []


def test_removed_provider_architecture_is_absent() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in APP_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    for removed in (
        "DEFAULT_REGISTRY",
        "ensure_mldsa_provider_registered",
        "map_mldsa_registration_container_to_nist",
        "acvp_mldsa",
    ):
        assert removed not in production
    assert not (APP_ROOT / "acvp_core" / "algorithm_provider.py").exists()
    assert not (APP_ROOT / "acvp_mldsa").exists()


def test_protocol_algorithms_response_is_descriptor_driven() -> None:
    service_path = APP_ROOT / "acvp_protocol" / "service.py"
    source = service_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "algorithms"
    )
    lines = source.splitlines()
    body = "\n".join(lines[function.lineno - 1 : function.end_lineno])

    assert "list_descriptors" in body
    assert "ML-DSA" not in body
    assert "parameterSets" not in body


def test_stage3_openapi_snapshot_is_parseable_and_strict_only() -> None:
    snapshot = APP_ROOT.parents[1] / "docs" / "baseline" / "openapi-stage3-algorithm-neutral.json"
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    paths = set(document["paths"])

    assert "/api/health" in paths
    assert all(path == "/api/health" or path.startswith("/acvp/v1/") for path in paths)


def test_stage3_documentation_records_module_and_dependency_boundaries() -> None:
    document = APP_ROOT.parents[1] / "docs" / "stages" / "stage3-algorithm-neutral-core.md"
    text = document.read_text(encoding="utf-8")

    assert "AlgorithmIdentity" in text
    assert "AlgorithmDescriptor" in text
    assert "AcvpAlgorithmModule" in text
    assert "TEST-ALGORITHM" in text
    assert "Stage 4" in text


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""
