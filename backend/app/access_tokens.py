from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from typing import Any, Dict, Optional

from .storage.store import get_access_token, save_access_token


DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 30 * 60
MIN_ACCESS_TOKEN_TTL_SECONDS = 60
MAX_ACCESS_TOKEN_TTL_SECONDS = 24 * 60 * 60


def issue_access_token(*, now: Optional[datetime] = None) -> Dict[str, Any]:
    issued_at = _utc_now(now)
    ttl_seconds = access_token_ttl_seconds()
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    token = secrets.token_urlsafe(32)
    save_access_token(
        _token_digest(token),
        created_at=issued_at.isoformat(),
        expires_at=expires_at.isoformat(),
    )
    return {
        "accessToken": token,
        "tokenType": "Bearer",
        "expiresIn": ttl_seconds,
        "expiresAt": expires_at.isoformat(),
    }


def access_token_status(token: str, *, now: Optional[datetime] = None) -> str:
    if not token:
        return "invalid"
    record = get_access_token(_token_digest(token))
    if record is None or record.get("revokedAt"):
        return "invalid"
    expires_at = _parse_timestamp(record.get("expiresAt"))
    if expires_at is None or expires_at <= _utc_now(now):
        return "expired"
    return "valid"


def access_token_ttl_seconds() -> int:
    raw = os.environ.get("ACVP_ACCESS_TOKEN_TTL_SECONDS")
    if raw is None:
        return DEFAULT_ACCESS_TOKEN_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("ACVP_ACCESS_TOKEN_TTL_SECONDS must be an integer.") from exc
    if not MIN_ACCESS_TOKEN_TTL_SECONDS <= value <= MAX_ACCESS_TOKEN_TTL_SECONDS:
        raise RuntimeError(
            "ACVP_ACCESS_TOKEN_TTL_SECONDS must be between 60 and 86400 seconds."
        )
    return value


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _utc_now(value: Optional[datetime] = None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
