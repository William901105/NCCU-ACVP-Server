from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.acvp_protocol import service
from app.genval import GenValArtifacts, GenValSettings


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "nist" / "mlkem"
PARAMETER_SETS = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
FUNCTIONS = [
    "encapsulation",
    "decapsulation",
    "encapsulationKeyCheck",
    "decapsulationKeyCheck",
]


@dataclass
class GenValController:
    calls: List[Tuple[str, str]] = field(default_factory=list)
    generation_error: Optional[BaseException] = None
    validation_error: Optional[BaseException] = None

    @property
    def validate_calls(self) -> int:
        return sum(phase == "validate" for phase, _ in self.calls)


def install_deterministic_genval(
    monkeypatch: Any,
    tmp_path: Path,
    *,
    provider_error: Optional[BaseException] = None,
) -> GenValController:
    """Install a deterministic test provider; this is not an IUT or production oracle."""
    source_dir = tmp_path / "third_party" / "nist-acvp-server"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "NIST_SOURCE.md").write_text(
        "- source git commit: deterministic-stage6-test-provider\n",
        encoding="utf-8",
    )
    settings = GenValSettings(
        project_root=tmp_path,
        runner_dll=tmp_path / "runner.dll",
        artifact_root=tmp_path / "artifacts",
        timeout_seconds=5,
    )
    controller = GenValController(generation_error=provider_error)

    class DeterministicNistProvider:
        def __init__(self, provider_settings: GenValSettings) -> None:
            self.settings = provider_settings

        def check_registration(self, registration: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
            controller.calls.append(("check", str(registration.get("mode"))))
            if controller.generation_error is not None:
                raise controller.generation_error
            work_dir.mkdir(parents=True, exist_ok=True)
            _write(work_dir / "check.stdout.txt", "deterministic check passed\n")
            _write(work_dir / "check.stderr.txt", "")
            return {"status": "passed"}

        def generate(self, registration: Dict[str, Any], work_dir: Path) -> GenValArtifacts:
            mode = str(registration["mode"])
            controller.calls.append(("generate", mode))
            if controller.generation_error is not None:
                raise controller.generation_error
            work_dir.mkdir(parents=True, exist_ok=True)
            prompt = load_fixture(mode, "prompt")
            expected = load_fixture(mode, "expectedResults")
            for payload in (prompt, expected):
                payload["vsId"] = registration["vsId"]
                payload["isSample"] = bool(registration.get("isSample", False))
            projection = {
                "vsId": registration["vsId"],
                "algorithm": "ML-KEM",
                "mode": mode,
                "revision": "FIPS203",
                "expectedResults": expected,
            }
            paths = {
                "registration": work_dir / "registration.json",
                "prompt": work_dir / "prompt.json",
                "internalProjection": work_dir / "internalProjection.json",
                "expectedResults": work_dir / "expectedResults.json",
            }
            for name, payload in (
                ("registration", registration),
                ("prompt", prompt),
                ("internalProjection", projection),
                ("expectedResults", expected),
            ):
                _write_json(paths[name], payload)
            _write(work_dir / "generation.stdout.txt", "deterministic generation passed\n")
            _write(work_dir / "generation.stderr.txt", "")
            return GenValArtifacts(
                registration=paths["registration"],
                prompt=paths["prompt"],
                internal_projection=paths["internalProjection"],
                expected_results=paths["expectedResults"],
                stdout=work_dir / "generation.stdout.txt",
                stderr=work_dir / "generation.stderr.txt",
            )

        def validate(self, internal_projection: Path, response: Path, work_dir: Path) -> Path:
            controller.calls.append(("validate", internal_projection.name))
            if controller.validation_error is not None:
                raise controller.validation_error
            projection = json.loads(internal_projection.read_text(encoding="utf-8"))
            received = json.loads(response.read_text(encoding="utf-8"))
            validation = validation_from_expected(
                projection["expectedResults"],
                received,
            )
            validation_path = work_dir / "validation.json"
            _write_json(validation_path, validation)
            _write(work_dir / "validation.stdout.txt", "deterministic validation completed\n")
            _write(work_dir / "validation.stderr.txt", "")
            return validation_path

    monkeypatch.setattr(service, "get_genval_settings", lambda: settings)
    monkeypatch.setattr(service, "NistCliGenValProvider", DeterministicNistProvider)
    return controller


def registration(mode: str) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "algorithm": "ML-KEM",
        "mode": mode,
        "revision": "FIPS203",
        "parameterSets": list(PARAMETER_SETS),
    }
    if mode == "encapDecap":
        value["functions"] = list(FUNCTIONS)
    return value


def session_request(
    *modes: str,
    is_sample: bool = True,
    auto_generate: bool = True,
) -> Dict[str, Any]:
    return {
        "algorithms": [registration(mode) for mode in modes],
        "isSample": is_sample,
        "autoGenerateVectorSets": auto_generate,
        "testsPerGroup": 1,
    }


def load_fixture(mode: str, artifact: str) -> Dict[str, Any]:
    return deepcopy(
        json.loads((FIXTURE_ROOT / mode / f"{artifact}.json").read_text(encoding="utf-8"))
    )


def body(response: Any) -> Dict[str, Any]:
    payload = response.json()
    assert isinstance(payload, list) and payload[0] == {"acvVersion": "1.0"}
    assert isinstance(payload[1], dict)
    return payload[1]


def error(response: Any) -> Dict[str, Any]:
    payload = body(response)
    assert payload.get("error") is not None
    return payload["error"]


def vector_url(session_id: str, vector_set_id: str) -> str:
    return f"/acvp/v1/testSessions/{session_id}/vectorSets/{vector_set_id}"


def flip_hex(value: str) -> str:
    replacement = "0" if value[0].upper() != "0" else "1"
    return replacement + value[1:]


def mutate_first_keygen_case(response: Dict[str, Any]) -> int:
    test = response["testGroups"][0]["tests"][0]
    test["ek"] = flip_hex(test["ek"])
    return int(test["tcId"])


def mutate_encap_functions(
    prompt: Dict[str, Any],
    response: Dict[str, Any],
) -> Dict[str, int]:
    prompt_functions = {group["tgId"]: group["function"] for group in prompt["testGroups"]}
    changed: Dict[str, int] = {}
    for group in response["testGroups"]:
        function = prompt_functions[group["tgId"]]
        if function in changed:
            continue
        test = group["tests"][0]
        if function == "encapsulation":
            test["c"] = flip_hex(test["c"])
        elif function == "decapsulation":
            test["k"] = flip_hex(test["k"])
        else:
            test["testPassed"] = not test["testPassed"]
        changed[function] = int(test["tcId"])
    assert set(changed) == set(FUNCTIONS)
    return changed


def validation_from_expected(
    expected: Dict[str, Any],
    received: Dict[str, Any],
) -> Dict[str, Any]:
    received_map = {(tg_id, tc_id): test for tg_id, tc_id, test in iter_tests(received)}
    tests: List[Dict[str, Any]] = []
    for tg_id, tc_id, expected_test in iter_tests(expected):
        passed = received_map.get((tg_id, tc_id)) == expected_test
        item: Dict[str, Any] = {
            "tgId": tg_id,
            "tcId": tc_id,
            "result": "passed" if passed else "failed",
        }
        if not passed:
            item["reason"] = "NIST-shaped deterministic test result mismatch"
        tests.append(item)
    return {
        "vsId": expected["vsId"],
        "disposition": "passed" if all(item["result"] == "passed" for item in tests) else "failed",
        "tests": tests,
    }


def iter_tests(payload: Dict[str, Any]) -> Iterable[Tuple[Any, Any, Dict[str, Any]]]:
    for group in payload.get("testGroups", []):
        for test in group.get("tests", []):
            yield group.get("tgId"), test.get("tcId"), test


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
