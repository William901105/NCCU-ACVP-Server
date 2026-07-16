from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError

from ..acvp_core.dependencies import get_algorithm_registry
from ..acvp_core.registry import AlgorithmModuleRegistry
from ..models import (
    AcvpV1TestSessionCreateRequest,
    AcvpV1TestSessionCertificationRequest,
    AcvpV1VectorSetGenerateRequest,
    AcvpV1VectorSetResultsSubmitRequest,
)
from .envelope import (
    AcvpEnvelopeError,
    acvp_envelope,
    envelope_response,
    parse_acvp_request,
)
from .errors import acvp_error_response
from .paging import parse_paging_params
from .service import (
    algorithms,
    cancel_vector_set,
    certify_test_session,
    create_test_session,
    delete_test_session,
    request_nist_vector_sets_for_session,
    get_test_session,
    get_test_session_results,
    get_test_session_vector_sets,
    get_request_resource,
    get_vector_set,
    get_vector_set_expected,
    get_vector_set_expected_results,
    get_vector_set_prompt,
    get_vector_set_results,
    legacy_python_session_response,
    legacy_vector_set_canonical_path,
    list_test_sessions,
    submit_test_session_for_validation,
    submit_vector_set_results,
    version,
)


router = APIRouter(prefix="/acvp/v1", tags=["ACVP v1"])


@router.get("/version")
def get_acvp_v1_version() -> Any:
    return _canonical_response(version())


@router.get("/algorithms")
def get_acvp_v1_algorithms(
    registry: AlgorithmModuleRegistry = Depends(get_algorithm_registry),
) -> Any:
    return _canonical_response(algorithms(registry))


@router.get("/testSessions")
def list_acvp_v1_test_sessions(
    status: Optional[str] = None,
    limit: Any = None,
    offset: Any = None,
) -> Any:
    paging = parse_paging_params(limit=limit, offset=offset)
    if isinstance(paging, JSONResponse):
        return _canonical_response(paging)
    return _canonical_response(
        list_test_sessions(status=status, limit=paging["limit"], offset=paging["offset"])
    )


@router.post("/testSessions")
def create_acvp_v1_test_session(
    payload: Any = Body(...),
    registry: AlgorithmModuleRegistry = Depends(get_algorithm_registry),
    response: Response = None,
) -> Any:
    request = _parse_session_create_request(payload)
    if isinstance(request, JSONResponse):
        return _canonical_response(request)
    if request["legacyBareBody"] and response is not None:
        _mark_deprecated_compatibility(response, "Use the canonical ACVP request envelope.")
    created = create_test_session(request["request"], registry)
    if response is None and isinstance(created, dict):
        created = legacy_python_session_response(created)
    return _canonical_response(created)


@router.get("/testSessions/{sessionId}")
def get_acvp_v1_test_session(sessionId: str) -> Any:
    return _canonical_response(get_test_session(sessionId))


@router.put("/testSessions/{sessionId}")
def certify_acvp_v1_test_session(
    sessionId: str,
    payload: Any = Body(...),
) -> Any:
    parsed = _parse_enveloped_model(payload, AcvpV1TestSessionCertificationRequest)
    if isinstance(parsed, JSONResponse):
        return _canonical_response(parsed)
    return _canonical_response(certify_test_session(sessionId, parsed))


@router.delete("/testSessions/{sessionId}")
def delete_acvp_v1_test_session(sessionId: str) -> Any:
    return _canonical_response(delete_test_session(sessionId))


@router.get("/testSessions/{sessionId}/vectorSets")
def get_acvp_v1_test_session_vector_sets(
    sessionId: str,
    status: Optional[str] = None,
    limit: Any = None,
    offset: Any = None,
) -> Any:
    paging = parse_paging_params(limit=limit, offset=offset)
    if isinstance(paging, JSONResponse):
        return _canonical_response(paging)
    return _canonical_response(
        get_test_session_vector_sets(
            sessionId,
            status=status,
            limit=paging["limit"],
            offset=paging["offset"],
        )
    )


@router.post("/testSessions/{sessionId}/vectorSets/generate")
def generate_acvp_v1_test_session_vector_sets(
    sessionId: str,
    payload: Any = Body(default=None),
    registry: AlgorithmModuleRegistry = Depends(get_algorithm_registry),
) -> Any:
    request = _parse_vector_set_generate_request(payload)
    if isinstance(request, JSONResponse):
        return _canonical_response(request)
    return _canonical_response(
        request_nist_vector_sets_for_session(sessionId, request, registry)
    )


@router.get("/testSessions/{sessionId}/vectorSets/{vsId:int}")
def get_acvp_v1_test_session_vector_set(sessionId: str, vsId: int) -> Any:
    return _canonical_response(
        get_vector_set_prompt(sessionId, vsId),
        add_server_metadata=False,
    )


@router.delete("/testSessions/{sessionId}/vectorSets/{vsId:int}")
def delete_acvp_v1_test_session_vector_set(sessionId: str, vsId: int) -> Any:
    return _canonical_response(cancel_vector_set(sessionId, vsId))


@router.get("/testSessions/{sessionId}/vectorSets/{vsId:int}/expected")
def get_acvp_v1_test_session_vector_set_expected(sessionId: str, vsId: int) -> Any:
    return _canonical_response(
        get_vector_set_expected(sessionId, vsId),
        add_server_metadata=False,
    )


@router.post("/testSessions/{sessionId}/vectorSets/{vsId:int}/results")
def submit_acvp_v1_test_session_vector_set_results(
    sessionId: str,
    vsId: int,
    payload: Any = Body(...),
    registry: AlgorithmModuleRegistry = Depends(get_algorithm_registry),
) -> Any:
    parsed = parse_acvp_results_submission_payload(payload)
    if isinstance(parsed, JSONResponse):
        return _canonical_response(parsed)
    return _canonical_response(
        submit_vector_set_results(
            sessionId,
            vsId,
            parsed["response"],
            registry,
            show_expected=parsed["showExpected"],
        )
    )


@router.put("/testSessions/{sessionId}/vectorSets/{vsId:int}/results")
def update_acvp_v1_test_session_vector_set_results(
    sessionId: str,
    vsId: int,
    payload: Any = Body(...),
    registry: AlgorithmModuleRegistry = Depends(get_algorithm_registry),
) -> Any:
    parsed = parse_acvp_results_submission_payload(payload)
    if isinstance(parsed, JSONResponse):
        return _canonical_response(parsed)
    return _canonical_response(
        submit_vector_set_results(
            sessionId,
            vsId,
            parsed["response"],
            registry,
            show_expected=parsed["showExpected"],
            update=True,
        )
    )


@router.get("/testSessions/{sessionId}/vectorSets/{vsId:int}/results")
def get_acvp_v1_test_session_vector_set_results(
    sessionId: str,
    vsId: int,
    showExpected: bool = False,
) -> Any:
    return _canonical_response(
        get_vector_set_results(sessionId, vsId, show_expected=showExpected)
    )


@router.get("/testSessions/{sessionId}/results")
def get_acvp_v1_test_session_results(sessionId: str) -> Any:
    return _canonical_response(get_test_session_results(sessionId))


@router.get("/requests/{requestId:int}")
def get_acvp_v1_request(requestId: int) -> Any:
    return _canonical_response(get_request_resource(requestId))


@router.post("/testSessions/{sessionId}/submit")
def submit_acvp_v1_test_session(sessionId: str, response: Response = None) -> Any:
    if response is not None:
        _mark_deprecated_compatibility(
            response,
            "Local finalization only; use PUT /acvp/v1/testSessions/{id} for certification.",
        )
    return _canonical_response(submit_test_session_for_validation(sessionId))


@router.get(
    "/testSessions/{sessionId}/vectorSets/{legacyVectorSetId}",
    include_in_schema=False,
)
def get_legacy_acvp_v1_vector_set(sessionId: str, legacyVectorSetId: str) -> Any:
    return _legacy_vector_redirect(sessionId, legacyVectorSetId)


@router.delete(
    "/testSessions/{sessionId}/vectorSets/{legacyVectorSetId}",
    include_in_schema=False,
)
def delete_legacy_acvp_v1_vector_set(sessionId: str, legacyVectorSetId: str) -> Any:
    return _legacy_vector_redirect(sessionId, legacyVectorSetId)


@router.get(
    "/testSessions/{sessionId}/vectorSets/{legacyVectorSetId}/expected",
    include_in_schema=False,
)
def get_legacy_acvp_v1_vector_set_expected(sessionId: str, legacyVectorSetId: str) -> Any:
    return _legacy_vector_redirect(sessionId, legacyVectorSetId, suffix="/expected")


@router.post(
    "/testSessions/{sessionId}/vectorSets/{legacyVectorSetId}/results",
    include_in_schema=False,
)
def post_legacy_acvp_v1_vector_set_results(sessionId: str, legacyVectorSetId: str) -> Any:
    return _legacy_vector_redirect(sessionId, legacyVectorSetId, suffix="/results")


@router.put(
    "/testSessions/{sessionId}/vectorSets/{legacyVectorSetId}/results",
    include_in_schema=False,
)
def put_legacy_acvp_v1_vector_set_results(sessionId: str, legacyVectorSetId: str) -> Any:
    return _legacy_vector_redirect(sessionId, legacyVectorSetId, suffix="/results")


@router.get(
    "/testSessions/{sessionId}/vectorSets/{legacyVectorSetId}/results",
    include_in_schema=False,
)
def get_legacy_acvp_v1_vector_set_results(sessionId: str, legacyVectorSetId: str) -> Any:
    return _legacy_vector_redirect(sessionId, legacyVectorSetId, suffix="/results")


# Kept as Python-level compatibility helpers only. They are deliberately not routes.
def get_acvp_v1_vector_set(vectorSetId: str) -> Any:
    return _canonical_response(get_vector_set(vectorSetId))


def delete_acvp_v1_vector_set(vectorSetId: str) -> Any:
    return _canonical_response(cancel_vector_set(None, vectorSetId))


def submit_acvp_v1_vector_set_results(
    vectorSetId: str,
    payload: Any,
    registry: AlgorithmModuleRegistry,
) -> Any:
    parsed = parse_acvp_results_submission_payload(payload)
    if isinstance(parsed, JSONResponse):
        return _canonical_response(parsed)
    return _canonical_response(
        submit_vector_set_results(
            None,
            vectorSetId,
            parsed["response"],
            registry,
            show_expected=parsed["showExpected"],
        )
    )


def get_acvp_v1_vector_set_results(vectorSetId: str, showExpected: bool = False) -> Any:
    return _canonical_response(
        get_vector_set_results(None, vectorSetId, show_expected=showExpected)
    )


def get_acvp_v1_vector_set_expected_results(vectorSetId: str) -> Any:
    return _canonical_response(get_vector_set_expected_results(vectorSetId))


def _canonical_response(value: Any, *, add_server_metadata: bool = True) -> Any:
    if isinstance(value, Response) and not isinstance(value, JSONResponse):
        return value
    if isinstance(value, JSONResponse):
        content = json.loads(value.body.decode("utf-8"))
        if _is_acvp_envelope(content):
            return value
        return JSONResponse(
            status_code=value.status_code,
            content=envelope_response(content),
            headers=_forwarded_headers(value),
        )
    return envelope_response(value) if add_server_metadata else acvp_envelope(value)


def _is_acvp_envelope(content: Any) -> bool:
    return (
        isinstance(content, list)
        and len(content) >= 2
        and isinstance(content[0], dict)
        and content[0].get("acvVersion") == "1.0"
    )


def _forwarded_headers(response: JSONResponse) -> dict[str, str]:
    request_id = response.headers.get("X-Request-ID")
    return {"X-Request-ID": request_id} if request_id else {}


def parse_acvp_results_submission_payload(payload: Any) -> Any:
    if isinstance(payload, AcvpV1VectorSetResultsSubmitRequest):
        return {"response": payload.response, "showExpected": False}
    if isinstance(payload, list):
        return _parse_acvp_results_envelope(payload)
    if isinstance(payload, dict):
        if "response" in payload:
            response = payload["response"]
            show_expected = _bool_value(payload.get("showExpected"))
            if isinstance(response, dict) and "showExpected" in response:
                response, nested_show_expected = _without_show_expected(response)
                show_expected = show_expected or nested_show_expected
            return {"response": response, "showExpected": show_expected}
        if _looks_like_vector_set_response(payload):
            response, show_expected = _without_show_expected(payload)
            return {"response": response, "showExpected": show_expected}
    return acvp_error_response(
        status_code=400,
        code="INVALID_REQUEST",
        message="Request body must be an ACVP response object or envelope.",
        path="$.response",
    )


def _parse_acvp_results_envelope(payload: list[Any]) -> Any:
    try:
        parsed = parse_acvp_request(payload)
    except AcvpEnvelopeError as exc:
        return _envelope_error_response(exc)
    response, show_expected = _without_show_expected(parsed.body)
    return {"response": response, "showExpected": show_expected}


def _parse_session_create_request(payload: Any) -> Any:
    if isinstance(payload, AcvpV1TestSessionCreateRequest):
        return {"request": payload, "legacyBareBody": True}
    try:
        parsed = parse_acvp_request(payload, allow_legacy_bare_body=True)
    except AcvpEnvelopeError as exc:
        return _envelope_error_response(exc)
    if "prompt" in parsed.body:
        return acvp_error_response(
            status_code=400,
            code="STRICT_REGISTRATION_REQUIRED",
            message="prompt sessions are not supported. Submit an algorithms registration container.",
            path="$.prompt",
        )
    if "autoGenerateExpectedResults" in parsed.body:
        return acvp_error_response(
            status_code=400,
            code="AUTO_EXPECTED_RESULTS_NOT_SUPPORTED",
            message="autoGenerateExpectedResults is not supported by the strict workflow.",
            path="$.autoGenerateExpectedResults",
        )
    request = _validate_strict_model(parsed.body, AcvpV1TestSessionCreateRequest)
    if isinstance(request, JSONResponse):
        return request
    return {"request": request, "legacyBareBody": parsed.legacy_bare_body}


def _parse_enveloped_model(payload: Any, model: Any) -> Any:
    try:
        parsed = parse_acvp_request(payload)
    except AcvpEnvelopeError as exc:
        return _envelope_error_response(exc)
    return _validate_strict_model(parsed.body, model)


def _envelope_error_response(exc: AcvpEnvelopeError) -> JSONResponse:
    return acvp_error_response(
        status_code=400,
        code=exc.code,
        message=exc.message,
        path=exc.path,
    )


def _parse_vector_set_generate_request(payload: Any) -> Any:
    payload = {} if payload is None else payload
    if isinstance(payload, AcvpV1VectorSetGenerateRequest):
        return payload
    return _validate_strict_model(payload, AcvpV1VectorSetGenerateRequest)


def _validate_strict_model(payload: Any, model: Any) -> Any:
    if not isinstance(payload, dict):
        return _invalid_request("Request body must be a JSON object.")
    if "generationProfile" in payload:
        return acvp_error_response(
            status_code=400,
            code="GENERATION_PROFILE_NOT_SUPPORTED",
            message="generationProfile is not supported. NCCU ACVP Server uses NIST GenVal only.",
            path="$.generationProfile",
        )
    for field in ("workflowPolicy", "executionBackend"):
        if field in payload:
            return acvp_error_response(
                status_code=400,
                code="CLIENT_POLICY_NOT_SUPPORTED",
                message=f"{field} is assigned by the NCCU ACVP Server.",
                path=f"$.{field}",
            )
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        return _invalid_request(_validation_error_message(exc))


def _invalid_request(message: str) -> JSONResponse:
    return acvp_error_response(
        status_code=400,
        code="INVALID_REQUEST",
        message=message,
        path="$",
    )


def _without_show_expected(body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    response = dict(body)
    return response, _bool_value(response.pop("showExpected", False))


def _bool_value(value: Any) -> bool:
    return value is True


def _looks_like_vector_set_response(payload: dict[str, Any]) -> bool:
    return bool({"vsId", "algorithm", "mode", "revision", "testGroups"}.intersection(payload))


def _validation_error_message(exc: ValidationError) -> str:
    errors = exc.errors(include_context=False)
    if not errors:
        return "Invalid request body."
    first = errors[0]
    location = ".".join(str(item) for item in first.get("loc", ()))
    if location:
        return f"{location}: {first.get('msg', 'Invalid request body.')}"
    return str(first.get("msg", "Invalid request body."))


def _legacy_vector_redirect(
    session_id: str,
    internal_vector_set_id: str,
    *,
    suffix: str = "",
) -> Any:
    target = legacy_vector_set_canonical_path(
        session_id,
        internal_vector_set_id,
        suffix=suffix,
    )
    if isinstance(target, JSONResponse):
        return _canonical_response(target)
    return RedirectResponse(
        url=target,
        status_code=308,
        headers={
            "Deprecation": "true",
            "Warning": '299 - "Legacy UUID vector-set URLs are deprecated"',
            "Link": f'<{target}>; rel="canonical"',
        },
    )


def _mark_deprecated_compatibility(response: Response, warning: str) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Warning"] = f'299 - "{warning}"'
