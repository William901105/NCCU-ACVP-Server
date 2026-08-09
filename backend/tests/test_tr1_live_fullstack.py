from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from helpers.mlkem_e2e import body, vector_url


REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    os.environ.get("NCCU_ACVP_LIVE_TR1") != "1",
    reason=(
        "set NCCU_ACVP_LIVE_TR1=1, start the patched Orleans host, and provide "
        "KYBER_PY_SRC to run the real tr1 full-stack workflow"
    ),
)


def test_mlkem_tr1_project_workflow_uses_prompt_only_and_nist_validation(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ACVP_GENVAL_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    registration = {
        "algorithm": "ML-KEM",
        "mode": "encapDecap",
        "revision": "FIPS203-tr1",
        "parameterSets": ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"],
        "functions": [
            "encapsulation",
            "decapsulation",
            "encapsulationKeyCheck",
            "decapsulationKeyCheck",
        ],
        "keyFormats": ["expanded", "seed"],
    }
    request = {
        "algorithms": [registration],
        "isSample": False,
        "autoGenerateVectorSets": True,
        "testsPerGroup": 1,
    }

    with TestClient(app) as client:
        created = body(client.post("/acvp/v1/testSessions", json=request))
        assert created["status"] == "vectorReady"
        url = vector_url(created["testSessionId"], created["vectorSetIds"][0])
        prompt = body(client.get(url))
        assert prompt["revision"] == "FIPS203-tr1"
        assert len(prompt["testGroups"]) == 15
        assert sum(len(group["tests"]) for group in prompt["testGroups"]) == 195
        dck_groups = [
            group for group in prompt["testGroups"]
            if group["function"] == "decapsulationKeyCheck"
        ]
        assert all(group["keyFormat"] == "expanded" for group in dck_groups)
        assert all("dk" in test for group in dck_groups for test in group["tests"])

        prompt_path = tmp_path / "prompt.json"
        prompt_path.write_text(json.dumps(prompt, indent=2) + "\n")
        source = os.environ.get("KYBER_PY_SRC")
        if not source:
            pytest.fail("KYBER_PY_SRC is required for live IUT acceptance")
        command = [
            sys.executable,
            str(REPO_ROOT / "IUT-tests" / "mlkem-native" / "run_test.py"),
            "--prompt",
            str(prompt_path),
            "--response-dir",
            str(tmp_path),
            "--variant",
            "pass",
            "--kyber-py-src",
            source,
        ]
        assert not any("internalProjection" in item for item in command)
        assert not any("expectedResults" in item for item in command)
        subprocess.run(command, check=True)

        response = json.loads(
            (tmp_path / "response_pass_encapDecap.json").read_text()
        )
        assert client.post(f"{url}/results", json={"response": response}).status_code == 204
        passed = body(client.get(f"{url}/results"))["results"]
        assert passed["disposition"] == "passed"
        assert {test["result"] for test in passed["tests"]} == {"passed"}

        wrong = copy.deepcopy(response)
        function_by_group = {
            group["tgId"]: group["function"] for group in prompt["testGroups"]
        }
        dck_response_group = next(
            group for group in wrong["testGroups"]
            if function_by_group[group["tgId"]] == "decapsulationKeyCheck"
        )
        changed = dck_response_group["tests"][0]
        changed["testPassed"] = not changed["testPassed"]
        assert client.put(f"{url}/results", json={"response": wrong}).status_code == 204
        failed = body(client.get(f"{url}/results"))["results"]
        assert failed["disposition"] == "fail"
        assert changed["tcId"] in {
            test["tcId"] for test in failed["tests"] if test["result"] == "fail"
        }

        summary = body(client.get(f"/acvp/v1/testSessions/{created['testSessionId']}"))
        vector = summary["vectorSets"][0]
        assert vector["provider"] == "nist-genval"
        assert vector["providerName"] == "NIST ACVP-Server GenValAppRunner"
        serialized = json.dumps(summary)
        assert "internalProjection" not in serialized
        assert "expectedResults" not in serialized
