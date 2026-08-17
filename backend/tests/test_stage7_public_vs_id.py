from __future__ import annotations

from copy import deepcopy
import json
import psycopg
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.store import (
    get_acvp_session,
    list_acvp_vector_sets_for_session,
    save_acvp_session,
    save_acvp_vector_set,
)
from helpers.mlkem_e2e import body, install_deterministic_genval, session_request


def envelope(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [{"acvVersion": "1.0"}, payload]


def create_session(client: TestClient, *modes: str) -> Dict[str, Any]:
    response = client.post(
        "/acvp/v1/testSessions",
        json=envelope(session_request(*modes)),
    )
    assert response.status_code == 200
    return body(response)


def test_numeric_vs_id_is_the_only_canonical_public_vector_identity(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = create_session(client, "keyGen", "encapDecap")
        session_id = created["testSessionId"]
        internal_records = list_acvp_vector_sets_for_session(session_id)
        internal_ids = [record["vectorSetId"] for record in internal_records]
        stored_session = get_acvp_session(session_id)
        stored_session["stateHistory"].append(
            {"event": "legacy", "metadata": {"vectorSetId": internal_ids[0]}}
        )
        save_acvp_session(stored_session)

        assert all(isinstance(vs_id, int) for vs_id in created["vsIds"])
        assert created["vectorSetIds"] == created["vsIds"]
        for vs_id, url in zip(created["vsIds"], created["vectorSetUrls"]):
            assert url.endswith(f"/{vs_id}")
            prompt = body(client.get(url))
            expected = body(client.get(f"{url}/expected"))
            assert prompt["vsId"] == expected["vsId"] == vs_id
            submitted = client.post(f"{url}/results", json=envelope(expected))
            assert submitted.status_code == 204
            vector_results = body(client.get(f"{url}/results"))
            assert vector_results["results"]["vsId"] == vs_id

        public_documents = [
            created,
            body(client.get(f"/acvp/v1/testSessions/{session_id}")),
            body(client.get(f"/acvp/v1/testSessions/{session_id}/vectorSets")),
            body(client.get(f"/acvp/v1/testSessions/{session_id}/results")),
        ]
        serialized = json.dumps(public_documents)
        assert all(internal_id not in serialized for internal_id in internal_ids)
        session_results = public_documents[-1]
        assert {
            int(item["vectorSetUrl"].rsplit("/", 1)[-1])
            for item in session_results["results"]
        } == set(created["vsIds"])


def test_numeric_mapping_is_session_scoped_persistent_and_legacy_uuid_redirects(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        first = create_session(client, "keyGen", "encapDecap")
        second = create_session(client, "keyGen")
        assert first["vsIds"][0] == second["vsIds"][0]

        missing = client.get(
            f"/acvp/v1/testSessions/{second['testSessionId']}/vectorSets/{first['vsIds'][1]}"
        )
        assert missing.status_code == 404

        internal_record = list_acvp_vector_sets_for_session(first["testSessionId"])[0]
        internal_id = internal_record["vectorSetId"]
        cross_session_legacy = client.get(
            f"/acvp/v1/testSessions/{second['testSessionId']}/vectorSets/{internal_id}",
            follow_redirects=False,
        )
        assert cross_session_legacy.status_code == 404
        assert internal_id not in cross_session_legacy.text
        legacy = client.get(
            f"/acvp/v1/testSessions/{first['testSessionId']}/vectorSets/{internal_id}",
            follow_redirects=False,
        )
        assert legacy.status_code == 308
        assert legacy.headers["Deprecation"] == "true"
        assert internal_id not in legacy.headers["location"]
        assert legacy.headers["location"].endswith(f"/{internal_record['vsId']}")

    with TestClient(app) as restarted_client:
        persisted = restarted_client.get(first["vectorSetUrls"][0])
        assert persisted.status_code == 200
        assert body(persisted)["vsId"] == first["vsIds"][0]


def test_same_session_duplicate_vs_id_is_rejected(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    install_deterministic_genval(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = create_session(client, "keyGen")

    original = list_acvp_vector_sets_for_session(created["testSessionId"])[0]
    duplicate = deepcopy(original)
    duplicate["vectorSetId"] = "duplicate-internal-record"
    with pytest.raises(psycopg.IntegrityError):
        save_acvp_vector_set(duplicate)


def test_openapi_canonical_vs_id_parameter_is_integer() -> None:
    operation = app.openapi()["paths"][
        "/acvp/v1/testSessions/{sessionId}/vectorSets/{vsId}"
    ]["get"]
    parameter = next(item for item in operation["parameters"] if item["name"] == "vsId")
    assert parameter["schema"]["type"] == "integer"
    assert all("legacyVectorSetId" not in path for path in app.openapi()["paths"])
