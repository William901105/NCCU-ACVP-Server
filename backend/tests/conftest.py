from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if not (BACKEND_ROOT / "app" / "storage").exists():
    cwd_backend = Path.cwd() / "backend"
    if (cwd_backend / "app" / "storage").exists():
        BACKEND_ROOT = cwd_backend
while str(BACKEND_ROOT) in sys.path:
    sys.path.remove(str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))
REPO_ROOT = BACKEND_ROOT.parent
MLKEM_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "nist" / "mlkem"


def _ensure_backend_app_package() -> None:
    loaded_app = sys.modules.get("app")
    if loaded_app is None:
        return
    app_file = Path(getattr(loaded_app, "__file__", "")).resolve()
    if str(app_file).startswith(str(BACKEND_ROOT)):
        return
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]


def _force_backend_app_package() -> None:
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        "app",
        BACKEND_ROOT / "app" / "__init__.py",
        submodule_search_locations=[str(BACKEND_ROOT / "app")],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["app"] = module
    spec.loader.exec_module(module)


_ensure_backend_app_package()


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path, monkeypatch):
    _ensure_backend_app_package()
    try:
        from app.storage.sqlite_store import reset_db_for_tests
    except ModuleNotFoundError:
        _force_backend_app_package()
        from app.storage.sqlite_store import reset_db_for_tests

    monkeypatch.setenv("ACVP_DB_PATH", str(tmp_path / "acvp_test.sqlite3"))
    reset_db_for_tests()
    yield
    reset_db_for_tests()


@pytest.fixture
def load_mlkem_fixture():
    def load(mode: str, artifact: str):
        path = MLKEM_FIXTURE_ROOT / mode / f"{artifact}.json"
        return __import__("json").loads(path.read_text(encoding="utf-8"))

    return load
