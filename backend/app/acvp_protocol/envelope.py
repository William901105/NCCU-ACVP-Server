from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List


WORKFLOW_POLICY = "strict"
EXECUTION_BACKEND = "nist-genval"
SERVER_METADATA: Dict[str, Any] = {
    "serverName": "NCCU ACVP Server",
    "workflowPolicy": WORKFLOW_POLICY,
    "executionBackend": EXECUTION_BACKEND,
}


class AcvpEnvelopeError(ValueError):
    def __init__(self, code: str, message: str, path: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


@dataclass(frozen=True)
class ParsedAcvpRequest:
    body: Dict[str, Any]
    acv_version: str
    legacy_bare_body: bool = False


def parse_acvp_request(
    payload: Any,
    *,
    allow_legacy_bare_body: bool = False,
) -> ParsedAcvpRequest:
    """Parse the protocol envelope without applying algorithm-specific rules."""
    if isinstance(payload, dict) and allow_legacy_bare_body:
        return ParsedAcvpRequest(
            body=copy.deepcopy(payload),
            acv_version="1.0",
            legacy_bare_body=True,
        )
    if not isinstance(payload, list):
        raise AcvpEnvelopeError(
            "INVALID_ACVP_ENVELOPE",
            "ACVP request must be a two-object JSON array.",
            "$",
        )
    if len(payload) != 2:
        raise AcvpEnvelopeError(
            "INVALID_ACVP_ENVELOPE",
            "ACVP envelope must contain exactly a version object and a body object.",
            "$",
        )
    version = payload[0]
    if not isinstance(version, dict) or set(version) != {"acvVersion"}:
        raise AcvpEnvelopeError(
            "INVALID_ACVP_ENVELOPE",
            "ACVP envelope version member must contain only acvVersion.",
            "$[0]",
        )
    acv_version = version.get("acvVersion")
    if acv_version != "1.0":
        raise AcvpEnvelopeError(
            "UNSUPPORTED_ACVP_VERSION",
            "Only acvVersion 1.0 is supported.",
            "$[0].acvVersion",
        )
    body = payload[1]
    if not isinstance(body, dict):
        raise AcvpEnvelopeError(
            "INVALID_ACVP_ENVELOPE",
            "ACVP envelope body must be a JSON object.",
            "$[1]",
        )
    return ParsedAcvpRequest(body=copy.deepcopy(body), acv_version=acv_version)


def acvp_envelope(body: Dict[str, Any], *, acv_version: str = "1.0") -> List[Dict[str, Any]]:
    return [{"acvVersion": acv_version}, copy.deepcopy(body)]


def server_metadata() -> Dict[str, Any]:
    return dict(SERVER_METADATA)


def with_server_metadata(body: Dict[str, Any]) -> Dict[str, Any]:
    """Add fixed server policy metadata without exposing local runtime fields."""
    result = copy.deepcopy(body)
    result.update(
        {
            "workflowPolicy": WORKFLOW_POLICY,
            "executionBackend": EXECUTION_BACKEND,
        }
    )
    return result


def envelope_response(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    return acvp_envelope(with_server_metadata(body))
