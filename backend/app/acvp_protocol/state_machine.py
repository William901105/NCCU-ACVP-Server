from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Set


class TestSessionStatus(str, Enum):
    CREATED = "created"
    CAPABILITIES_ACCEPTED = "capabilitiesAccepted"
    VECTOR_READY = "vectorReady"
    VECTOR_DOWNLOADED = "vectorDownloaded"
    RESULTS_SUBMITTED = "resultsSubmitted"
    VALIDATING = "validating"
    VALIDATED = "validated"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class VectorSetStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    DOWNLOADED = "downloaded"
    RESULTS_SUBMITTED = "resultsSubmitted"
    VALIDATING = "validating"
    VALIDATED = "validated"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_STATUSES = {
    TestSessionStatus.CANCELLED.value,
    TestSessionStatus.EXPIRED.value,
}

SESSION_TRANSITIONS: Dict[str, Set[str]] = {
    TestSessionStatus.CREATED.value: {
        TestSessionStatus.CAPABILITIES_ACCEPTED.value,
        TestSessionStatus.VECTOR_READY.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.CAPABILITIES_ACCEPTED.value: {
        TestSessionStatus.VECTOR_READY.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.VECTOR_READY.value: {
        TestSessionStatus.VECTOR_DOWNLOADED.value,
        TestSessionStatus.RESULTS_SUBMITTED.value,
        TestSessionStatus.VALIDATING.value,
        TestSessionStatus.VALIDATED.value,
        TestSessionStatus.FAILED.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.VECTOR_DOWNLOADED.value: {
        TestSessionStatus.RESULTS_SUBMITTED.value,
        TestSessionStatus.VALIDATING.value,
        TestSessionStatus.VALIDATED.value,
        TestSessionStatus.FAILED.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.RESULTS_SUBMITTED.value: {
        TestSessionStatus.VALIDATING.value,
        TestSessionStatus.VALIDATED.value,
        TestSessionStatus.FAILED.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.VALIDATING.value: {
        TestSessionStatus.RESULTS_SUBMITTED.value,
        TestSessionStatus.VALIDATED.value,
        TestSessionStatus.FAILED.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.VALIDATED.value: {
        TestSessionStatus.RESULTS_SUBMITTED.value,
        TestSessionStatus.VALIDATING.value,
        TestSessionStatus.FAILED.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.FAILED.value: {
        TestSessionStatus.RESULTS_SUBMITTED.value,
        TestSessionStatus.VALIDATING.value,
        TestSessionStatus.VALIDATED.value,
        TestSessionStatus.CANCELLED.value,
        TestSessionStatus.EXPIRED.value,
    },
    TestSessionStatus.CANCELLED.value: set(),
    TestSessionStatus.EXPIRED.value: set(),
}

VECTOR_TRANSITIONS: Dict[str, Set[str]] = {
    VectorSetStatus.CREATED.value: {
        VectorSetStatus.READY.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.READY.value: {
        VectorSetStatus.DOWNLOADED.value,
        VectorSetStatus.RESULTS_SUBMITTED.value,
        VectorSetStatus.VALIDATING.value,
        VectorSetStatus.VALIDATED.value,
        VectorSetStatus.FAILED.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.DOWNLOADED.value: {
        VectorSetStatus.RESULTS_SUBMITTED.value,
        VectorSetStatus.VALIDATING.value,
        VectorSetStatus.VALIDATED.value,
        VectorSetStatus.FAILED.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.RESULTS_SUBMITTED.value: {
        VectorSetStatus.VALIDATING.value,
        VectorSetStatus.VALIDATED.value,
        VectorSetStatus.FAILED.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.VALIDATING.value: {
        VectorSetStatus.RESULTS_SUBMITTED.value,
        VectorSetStatus.VALIDATED.value,
        VectorSetStatus.FAILED.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.VALIDATED.value: {
        VectorSetStatus.RESULTS_SUBMITTED.value,
        VectorSetStatus.VALIDATING.value,
        VectorSetStatus.FAILED.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.FAILED.value: {
        VectorSetStatus.RESULTS_SUBMITTED.value,
        VectorSetStatus.VALIDATING.value,
        VectorSetStatus.VALIDATED.value,
        VectorSetStatus.CANCELLED.value,
        VectorSetStatus.EXPIRED.value,
    },
    VectorSetStatus.CANCELLED.value: set(),
    VectorSetStatus.EXPIRED.value: set(),
}


class StateTransitionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        path: str,
        *,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.from_status = from_status
        self.to_status = to_status


def now_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_state_event(
    entity: Dict[str, Any],
    *,
    event: str,
    from_status: Optional[str],
    to_status: str,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    entry: Dict[str, Any] = {
        "at": now_timestamp(),
        "event": event,
        "from": from_status,
        "to": to_status,
        "reason": reason,
    }
    if metadata:
        entry["metadata"] = metadata
    entity.setdefault("stateHistory", []).append(entry)
    storage_identity = _state_event_storage_identity(entity)
    if storage_identity is not None:
        entity_type, entity_id = storage_identity
        from ..storage.store import record_state_event

        details: Dict[str, Any] = {"reason": reason}
        if metadata:
            details["metadata"] = metadata
        record_state_event(
            entity_type,
            entity_id,
            from_status,
            to_status,
            event,
            details=details,
        )


def transition_session(
    session: Dict[str, Any],
    to_status: str,
    *,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    assert_session_transition_allowed(session, to_status)
    from_status = session["status"]
    session["status"] = to_status
    session["updatedAt"] = now_timestamp()
    add_state_event(
        session,
        event=_event_for_status(to_status),
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        metadata=metadata,
    )


def transition_vector_set(
    vector_set: Dict[str, Any],
    to_status: str,
    *,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    assert_vector_transition_allowed(vector_set, to_status)
    from_status = vector_set["status"]
    vector_set["status"] = to_status
    vector_set["updatedAt"] = now_timestamp()
    add_state_event(
        vector_set,
        event=_event_for_status(to_status),
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        metadata=metadata,
    )


def assert_session_transition_allowed(session: Dict[str, Any], to_status: str) -> None:
    from_status = session.get("status")
    if not isinstance(from_status, str):
        raise StateTransitionError(
            "INVALID_SESSION_STATE",
            "Test session has no valid status.",
            _session_path(session),
            from_status=None,
            to_status=to_status,
        )
    if to_status == from_status:
        raise StateTransitionError(
            "INVALID_SESSION_STATE_TRANSITION",
            f"Test session is already {to_status}.",
            _session_path(session),
            from_status=from_status,
            to_status=to_status,
        )
    if to_status not in {item.value for item in TestSessionStatus}:
        raise StateTransitionError(
            "INVALID_SESSION_STATUS",
            f"Unsupported test session status: {to_status}.",
            _session_path(session),
            from_status=from_status,
            to_status=to_status,
        )
    if to_status not in SESSION_TRANSITIONS.get(from_status, set()):
        raise StateTransitionError(
            "INVALID_SESSION_STATE_TRANSITION",
            f"Cannot transition test session from {from_status} to {to_status}.",
            _session_path(session),
            from_status=from_status,
            to_status=to_status,
        )


def assert_vector_transition_allowed(vector_set: Dict[str, Any], to_status: str) -> None:
    from_status = vector_set.get("status")
    if not isinstance(from_status, str):
        raise StateTransitionError(
            "INVALID_VECTOR_SET_STATE",
            "Vector set has no valid status.",
            _vector_path(vector_set),
            from_status=None,
            to_status=to_status,
        )
    if to_status == from_status:
        raise StateTransitionError(
            "INVALID_VECTOR_SET_STATE_TRANSITION",
            f"Vector set is already {to_status}.",
            _vector_path(vector_set),
            from_status=from_status,
            to_status=to_status,
        )
    if to_status not in {item.value for item in VectorSetStatus}:
        raise StateTransitionError(
            "INVALID_VECTOR_SET_STATUS",
            f"Unsupported vector set status: {to_status}.",
            _vector_path(vector_set),
            from_status=from_status,
            to_status=to_status,
        )
    if to_status not in VECTOR_TRANSITIONS.get(from_status, set()):
        raise StateTransitionError(
            "INVALID_VECTOR_SET_STATE_TRANSITION",
            f"Cannot transition vector set from {from_status} to {to_status}.",
            _vector_path(vector_set),
            from_status=from_status,
            to_status=to_status,
        )


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def session_is_expired(session: Dict[str, Any]) -> bool:
    return _is_expired(session.get("expiresAt"))


def vector_set_is_expired(vector_set: Dict[str, Any]) -> bool:
    return _is_expired(vector_set.get("expiresAt"))


def _is_expired(expires_at: Any) -> bool:
    if not expires_at:
        return False
    if not isinstance(expires_at, str):
        return False
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= parsed


def _event_for_status(status: str) -> str:
    if status == TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return "capabilitiesAccepted"
    if status == TestSessionStatus.VECTOR_READY.value:
        return "vectorReady"
    if status == TestSessionStatus.VECTOR_DOWNLOADED.value:
        return "vectorDownloaded"
    if status == VectorSetStatus.DOWNLOADED.value:
        return "downloaded"
    if status == TestSessionStatus.RESULTS_SUBMITTED.value:
        return "resultsSubmitted"
    return status


def _session_path(session: Dict[str, Any]) -> str:
    session_id = session.get("testSessionId", "<unknown>")
    return f"/acvp/v1/testSessions/{session_id}"


def _vector_path(vector_set: Dict[str, Any]) -> str:
    vector_set_id = vector_set.get("vectorSetId", "<unknown>")
    return f"/acvp/v1/vectorSets/{vector_set_id}"


def _state_event_storage_identity(entity: Dict[str, Any]) -> Optional[tuple[str, str]]:
    if entity.get("vectorSetId") is not None:
        return ("acvp_vector_set", str(entity["vectorSetId"]))
    if entity.get("testSessionId") is not None:
        return ("acvp_session", str(entity["testSessionId"]))
    if entity.get("sessionId") is not None:
        return ("demo_session", str(entity["sessionId"]))
    return None
