from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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

TEST_DATABASE_URL = os.environ.get("ACVP_TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "ACVP_TEST_DATABASE_URL must point to the dedicated PostgreSQL "
        "test database, for example acvp_test."
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ACVP_DATABASE_URL"] = TEST_DATABASE_URL


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
def isolated_postgres_db(monkeypatch):
    _ensure_backend_app_package()
    try:
        from app.storage.postgres_store import reset_db_for_tests
    except ModuleNotFoundError:
        _force_backend_app_package()
        from app.storage.postgres_store import reset_db_for_tests

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("ACVP_DATABASE_URL", TEST_DATABASE_URL)
    reset_db_for_tests()
    from app.access_tokens import issue_access_token

    token = issue_access_token()["accessToken"]
    original_request = TestClient.request

    def authenticated_request(client, method, url, *args, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        if not any(name.lower() == "authorization" for name in headers):
            headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        return original_request(client, method, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", authenticated_request)
    yield
    reset_db_for_tests()


@pytest.fixture
def load_mlkem_fixture():
    def load(mode: str, artifact: str):
        path = MLKEM_FIXTURE_ROOT / mode / f"{artifact}.json"
        return __import__("json").loads(path.read_text(encoding="utf-8"))

    return load
