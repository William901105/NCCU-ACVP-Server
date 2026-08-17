from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from fastapi.testclient import TestClient

from app.access_tokens import issue_access_token
from app.main import app
from app.storage.postgres_store import connect


def body(response):
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0] == {"acvVersion": "1.0"}
    return payload[1]


def test_access_token_is_required_and_db_backed(monkeypatch) -> None:
    monkeypatch.setenv("ACVP_ACCESS_TOKEN_TTL_SECONDS", "1800")

    with TestClient(app) as client:
        unauthorized = client.get(
            "/acvp/v1/version",
            headers={"Authorization": ""},
        )
        assert unauthorized.status_code == 401
        assert body(unauthorized)["error"]["code"] == "ACCESS_TOKEN_REQUIRED"
        assert unauthorized.headers["WWW-Authenticate"] == "Bearer"

        issued_response = client.post("/acvp/v1/accessTokens")
        assert issued_response.status_code == 200
        issued = body(issued_response)
        assert issued["tokenType"] == "Bearer"
        assert issued["expiresIn"] == 1800

        authorized = client.get(
            "/acvp/v1/version",
            headers={"Authorization": f"Bearer {issued['accessToken']}"},
        )
        assert authorized.status_code == 200

    digest = hashlib.sha256(issued["accessToken"].encode("utf-8")).hexdigest()
    conn = connect()
    try:
        stored = conn.execute(
            "SELECT token_digest, expires_at FROM access_tokens WHERE token_digest = ?",
            (digest,),
        ).fetchone()
    finally:
        conn.close()
    assert stored is not None
    assert stored["token_digest"] == digest
    assert issued["accessToken"] not in str(stored)


def test_invalid_and_expired_access_tokens_return_401(monkeypatch) -> None:
    expired = issue_access_token(now=datetime(2020, 1, 1, tzinfo=timezone.utc))

    with TestClient(app) as client:
        invalid = client.get(
            "/acvp/v1/algorithms",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        expired_response = client.get(
            "/acvp/v1/algorithms",
            headers={"Authorization": f"Bearer {expired['accessToken']}"},
        )

    assert invalid.status_code == 401
    assert body(invalid)["error"]["code"] == "INVALID_ACCESS_TOKEN"
    assert expired_response.status_code == 401
    assert body(expired_response)["error"]["code"] == "ACCESS_TOKEN_EXPIRED"
