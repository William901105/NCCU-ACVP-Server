#!/usr/bin/env python3
"""Run real ML-DSA and ML-KEM IUT flows through the published frontend URL."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
ACVP_VERSION = {"acvVersion": "1.0"}
CAMPAIGN_SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"
PREREQUISITES = [{"algorithm": "SHA", "valValue": "same"}]


def mldsa_capabilities() -> List[Dict[str, Any]]:
    return [
        {
            "parameterSets": ["ML-DSA-44"],
            "messageLength": [{"min": 8, "max": 128, "increment": 8}],
            "contextLength": [{"min": 0, "max": 64, "increment": 8}],
            "hashAlgs": ["SHA2-256"],
        }
    ]


CASES: List[Dict[str, Any]] = [
    {
        "name": "mldsa-keygen",
        "runner": "mldsa-native",
        "mode": "keyGen",
        "registration": {
            "algorithm": "ML-DSA",
            "mode": "keyGen",
            "revision": "FIPS204",
            "prereqVals": PREREQUISITES,
            "parameterSets": ["ML-DSA-44"],
        },
    },
    {
        "name": "mldsa-siggen-tr1",
        "runner": "mldsa-native",
        "mode": "sigGen",
        "registration": {
            "algorithm": "ML-DSA",
            "mode": "sigGen",
            "revision": "FIPS204-tr1",
            "prereqVals": PREREQUISITES,
            "signatureInterfaces": ["internal", "external"],
            "externalMu": [False, True],
            "preHash": ["pure", "preHash"],
            "capabilities": mldsa_capabilities(),
            "deterministic": [True, False],
            "keyFormats": ["expanded", "seed"],
        },
    },
    {
        "name": "mldsa-sigver",
        "runner": "mldsa-native",
        "mode": "sigVer",
        "registration": {
            "algorithm": "ML-DSA",
            "mode": "sigVer",
            "revision": "FIPS204",
            "prereqVals": PREREQUISITES,
            "signatureInterfaces": ["internal", "external"],
            "externalMu": [False, True],
            "preHash": ["pure", "preHash"],
            "capabilities": mldsa_capabilities(),
        },
    },
    {
        "name": "mlkem-keygen",
        "runner": "mlkem-native",
        "mode": "keyGen",
        "registration": {
            "algorithm": "ML-KEM",
            "mode": "keyGen",
            "revision": "FIPS203",
            "prereqVals": PREREQUISITES,
            "parameterSets": ["ML-KEM-512"],
        },
    },
    {
        "name": "mlkem-encapdecap",
        "runner": "mlkem-native",
        "mode": "encapDecap",
        "registration": {
            "algorithm": "ML-KEM",
            "mode": "encapDecap",
            "revision": "FIPS203",
            "prereqVals": PREREQUISITES,
            "parameterSets": ["ML-KEM-512"],
            "functions": [
                "encapsulation",
                "decapsulation",
                "encapsulationKeyCheck",
                "decapsulationKeyCheck",
            ],
        },
    },
]


class AcvpClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        expected_status: int = 200,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=360) as response:
                status = response.status
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read()
            raise RuntimeError(
                f"{method} {path} returned HTTP {exc.code}: "
                f"{raw.decode('utf-8', errors='replace')}"
            ) from exc
        if status != expected_status:
            raise RuntimeError(f"{method} {path} returned HTTP {status}, expected {expected_status}")
        return None if not raw else json.loads(raw)

    @staticmethod
    def body(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], dict):
            raise RuntimeError(f"Expected an ACVP envelope, got: {payload!r}")
        return payload[1]

    def authenticate(self) -> None:
        body = self.body(self.request("POST", "/acvp/v1/accessTokens"))
        self.token = str(body["accessToken"])


def run_case(client: AcvpClient, case: Dict[str, Any], root: Path) -> Dict[str, Any]:
    started = time.monotonic()
    print(f"[{case['name']}] creating NIST GenVal session", flush=True)
    create_body = {
        "algorithms": [case["registration"]],
        "label": f"docker-e2e-{case['name']}",
        "autoGenerateVectorSets": True,
        "campaignSeed": CAMPAIGN_SEED,
        "testsPerGroup": 1,
        "isSample": False,
    }
    created = client.body(
        client.request("POST", "/acvp/v1/testSessions", [ACVP_VERSION, create_body])
    )
    session_id = str(created["testSessionId"])
    vector_sets = created.get("vectorSets") or []
    if not vector_sets:
        vector_sets = client.body(
            client.request("GET", f"/acvp/v1/testSessions/{session_id}/vectorSets")
        ).get("vectorSets", [])
    if len(vector_sets) != 1:
        raise RuntimeError(f"{case['name']} expected exactly one vector set: {vector_sets!r}")
    vs_id = int(vector_sets[0]["vsId"])
    vector_path = f"/acvp/v1/testSessions/{session_id}/vectorSets/{vs_id}"
    prompt = client.request("GET", vector_path)
    prompt_body = client.body(prompt)

    case_dir = root / case["name"]
    case_dir.mkdir(parents=True)
    prompt_path = case_dir / "prompt.json"
    prompt_path.write_text(json.dumps(prompt, indent=2) + "\n", encoding="utf-8")

    runner = REPO_ROOT / "IUT-tests" / case["runner"] / "run_test.py"
    subprocess.run(
        [
            sys.executable,
            str(runner),
            "--prompt",
            str(prompt_path),
            "--response-dir",
            str(case_dir),
            "--variant",
            "both",
            "--expect-mode",
            case["mode"],
        ],
        cwd=str(REPO_ROOT),
        check=True,
    )

    pass_response = json.loads(
        (case_dir / f"response_pass_{case['mode']}.json").read_text(encoding="utf-8")
    )
    fail_response = json.loads(
        (case_dir / f"response_fail_{case['mode']}.json").read_text(encoding="utf-8")
    )

    dispositions = []
    client.request("POST", f"{vector_path}/results", [ACVP_VERSION, pass_response], expected_status=204)
    dispositions.append(result_disposition(client, vector_path, "passed"))
    client.request("PUT", f"{vector_path}/results", [ACVP_VERSION, fail_response], expected_status=204)
    dispositions.append(result_disposition(client, vector_path, "fail"))
    client.request("PUT", f"{vector_path}/results", [ACVP_VERSION, pass_response], expected_status=204)
    dispositions.append(result_disposition(client, vector_path, "passed"))

    session_results = client.body(
        client.request("GET", f"/acvp/v1/testSessions/{session_id}/results")
    )
    if session_results.get("passed") is not True:
        raise RuntimeError(f"{case['name']} session did not finish passed: {session_results!r}")

    group_count = len(prompt_body.get("testGroups", []))
    test_count = sum(len(group.get("tests", [])) for group in prompt_body.get("testGroups", []))
    summary = {
        "name": case["name"],
        "algorithm": case["registration"]["algorithm"],
        "mode": case["mode"],
        "revision": case["registration"]["revision"],
        "sessionId": session_id,
        "vsId": vs_id,
        "testGroupCount": group_count,
        "testCaseCount": test_count,
        "dispositions": dispositions,
        "finalPassed": True,
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }
    print(f"[{case['name']}] passed ({group_count} groups, {test_count} tests)", flush=True)
    return summary


def result_disposition(client: AcvpClient, vector_path: str, expected: str) -> str:
    payload = client.body(client.request("GET", f"{vector_path}/results"))
    disposition = str(payload["results"]["disposition"])
    if disposition != expected:
        raise RuntimeError(f"Expected disposition {expected!r}, got {disposition!r}")
    return disposition


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--verify-existing",
        type=Path,
        help="Verify that all session IDs from an earlier output remain passed.",
    )
    args = parser.parse_args()

    started = time.monotonic()
    client = AcvpClient(args.base_url)
    client.authenticate()
    if args.verify_existing:
        previous = json.loads(args.verify_existing.read_text(encoding="utf-8"))
        verified = []
        for session_id in previous.get("sessionIds", []):
            results = client.body(
                client.request("GET", f"/acvp/v1/testSessions/{session_id}/results")
            )
            if results.get("passed") is not True:
                raise RuntimeError(f"Persisted session {session_id} is not passed: {results!r}")
            verified.append(session_id)
        report = {
            "baseUrl": args.base_url,
            "verifiedSessionIds": verified,
            "verifiedCount": len(verified),
            "allPassed": len(verified) == len(previous.get("sessionIds", [])),
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }
        print(json.dumps(report, indent=2) + "\n")
        return 0

    with tempfile.TemporaryDirectory(prefix="nccu-acvp-docker-e2e-") as directory:
        summaries = [run_case(client, case, Path(directory)) for case in CASES]
    report = {
        "baseUrl": args.base_url,
        "caseCount": len(summaries),
        "cases": summaries,
        "sessionIds": [item["sessionId"] for item in summaries],
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
