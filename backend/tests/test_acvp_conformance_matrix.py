from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
GENVAL_DOC = ROOT / "docs" / "nist-genval-integration.md"
STAGE1_DOC = ROOT / "docs" / "stages" / "stage1-strict-policy.md"
STAGE2_DOC = ROOT / "docs" / "stages" / "stage2-remove-local-runtime.md"
STAGE2_OPENAPI = ROOT / "docs" / "baseline" / "openapi-stage2-strict.json"


def test_strict_runtime_docs_describe_nist_only_execution() -> None:
    for document in (README, GENVAL_DOC, STAGE1_DOC, STAGE2_DOC):
        assert document.exists()

    text = (README.read_text(encoding="utf-8") + GENVAL_DOC.read_text(encoding="utf-8"))
    assert "NIST GenVal" in text
    assert "does not use a Python fallback" in text
    assert "internal projection" in text.lower()


def test_stage2_doc_records_removed_runtime_and_legacy_storage_policy() -> None:
    text = STAGE2_DOC.read_text(encoding="utf-8")

    assert "`/acvp/v1/*` plus `/api/health`" in text
    assert "SQLite schema is not migrated" in text
    assert "`imports` and `demo_sessions` tables remain" in text
    assert "never use a fallback" in text


def test_stage2_openapi_snapshot_has_only_strict_routes() -> None:
    document = json.loads(STAGE2_OPENAPI.read_text(encoding="utf-8"))
    paths = set(document["paths"])

    assert "/api/health" in paths
    assert all(path == "/api/health" or path.startswith("/acvp/v1/") for path in paths)
    assert "/api/import" not in paths
    assert "/api/demo/clear" not in paths
