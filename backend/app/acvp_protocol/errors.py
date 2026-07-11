from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from .envelope import envelope_response, server_metadata
from .request_context import get_or_create_request_id


class AcvpProtocolError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.path = path
        self.details = details


def acvp_error_body(
    *,
    code: str,
    message: str,
    path: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    request: Optional[Request] = None,
) -> Dict[str, Any]:
    resolved_request_id = request_id or get_or_create_request_id(request)
    error: Dict[str, Any] = {
        "code": code,
        "message": message,
        "path": path or "$",
        "requestId": resolved_request_id,
    }
    if details:
        error["details"] = details
    return {
        "error": error,
        **server_metadata(),
    }


def acvp_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    path: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    request: Optional[Request] = None,
    enveloped: bool = False,
) -> JSONResponse:
    body = acvp_error_body(
        code=code,
        message=message,
        path=path,
        details=details,
        request_id=request_id,
        request=request,
    )
    response_body: Any = (
        envelope_response(body)
        if enveloped
        else body
    )
    return JSONResponse(
        status_code=status_code,
        content=response_body,
        headers={"X-Request-ID": body["error"]["requestId"]},
    )


def invalid_query_error(
    *,
    parameter: str,
    value: Any,
    message: str,
    path: Optional[str] = None,
) -> JSONResponse:
    return acvp_error_response(
        status_code=400,
        code="INVALID_QUERY_PARAMETER",
        message=message,
        path=path or f"$.{parameter}",
        details={"parameter": parameter, "value": value},
    )


def unknown_session_error(session_id: str, path: Optional[str] = None) -> JSONResponse:
    return acvp_error_response(
        status_code=404,
        code="UNKNOWN_TEST_SESSION",
        message="Unknown testSessionId.",
        path=path or f"/acvp/v1/testSessions/{session_id}",
        details={"testSessionId": session_id},
    )


def unknown_vector_set_error(vector_set_id: str, path: Optional[str] = None) -> JSONResponse:
    return acvp_error_response(
        status_code=404,
        code="UNKNOWN_VECTOR_SET",
        message="Unknown vectorSetId.",
        path=path or f"/acvp/v1/vectorSets/{vector_set_id}",
        details={"vectorSetId": vector_set_id},
    )


def invalid_state_error(
    *,
    code: str,
    message: str,
    path: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    return acvp_error_response(
        status_code=409,
        code=code,
        message=message,
        path=path,
        details=details,
    )


def invalid_envelope_error(
    *,
    code: str = "INVALID_ACVP_ENVELOPE",
    message: str,
    path: Optional[str] = None,
) -> JSONResponse:
    return acvp_error_response(
        status_code=400,
        code=code,
        message=message,
        path=path,
    )


def schema_error_response(exc: Any) -> JSONResponse:
    return acvp_error_response(
        status_code=400,
        code=getattr(exc, "code", "SCHEMA_ERROR"),
        message=getattr(exc, "message", str(exc)),
        path=getattr(exc, "path", "$"),
    )
