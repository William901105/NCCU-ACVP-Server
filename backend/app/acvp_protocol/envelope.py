from __future__ import annotations

import copy
from typing import Any, Dict, List


WORKFLOW_POLICY = "strict"
EXECUTION_BACKEND = "nist-genval"
SERVER_METADATA: Dict[str, Any] = {
    "serverName": "NCCU ACVP Server",
    "workflowPolicy": WORKFLOW_POLICY,
    "executionBackend": EXECUTION_BACKEND,
}


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
