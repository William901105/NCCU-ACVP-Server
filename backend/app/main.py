from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .acvp_mldsa.errors import AcvpSchemaError
from .acvp_mldsa.expected import (
    generate_expected_results_from_prompt,
    generate_keygen_expected_results_from_prompt,
)
from .acvp_mldsa.validators import (
    validate_mldsa_registration,
    validate_mldsa_response,
    validate_mldsa_vector_set,
)
from .acvp_protocol.routes import router as acvp_v1_router
from .acvp_protocol.errors import acvp_error_response
from .acvp_protocol.request_context import (
    get_or_create_request_id,
    reset_request_id,
    set_request_id,
)
from .acvp_parser import AcvpParseError, normalize_acvp_json, summarize_vector_set
from .crypto_oracle.mldsa_oracle import (
    MldsaOracleError,
    MldsaOracleInputError,
    keygen_internal,
    siggen_internal,
    sigver_internal,
)
from .models import (
    DemoAcvpResponseSubmitRequest,
    DemoAcvpSessionCreateRequest,
    GeneratedKeygenImportRequest,
    GeneratedMldsaImportRequest,
    ImportRequest,
    ImportSummary,
    LoadSampleRequest,
    MldsaExpectedResultsRequest,
    MldsaExpectedResultsResponse,
    MldsaKeygenExpectedResultsRequest,
    MldsaKeygenExpectedResultsResponse,
    MldsaKeygenRequest,
    MldsaKeygenResponse,
    MldsaSigGenRequest,
    MldsaSigGenResponse,
    MldsaSigVerRequest,
    MldsaSigVerResponse,
    ValidateRequest,
)
from .report import build_report
from .sample_loader import SampleLoaderError, list_sample_data, load_sample
from .storage.sqlite_store import (
    DEMO_SESSION_STORE,
    IMPORT_STORE,
    delete_demo_session as delete_demo_session_record,
    get_db_path,
    get_import_record,
    init_db,
    list_demo_sessions as list_demo_session_records,
    record_state_event,
    reset_db_for_tests,
    save_demo_session,
    save_import_record,
    update_import_validation,
)
from .validator import validate


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FIPS 204 / ML-DSA ACVP JSON Viewer + Local Validator",
    version="0.1.0",
    description="Local JSON comparison demo for ML-DSA ACVP prompt, expectedResults, and response files.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(acvp_v1_router)

LEGACY_ORACLE_DESCRIPTION = (
    "Legacy/debug-only local ML-DSA oracle endpoint. Formal /acvp/v1 strict "
    "generation and validation use the NIST GenVal adapter, not this endpoint."
)


@app.middleware("http")
async def acvp_request_id_middleware(request: Request, call_next):
    token = set_request_id(request.headers.get("X-Request-ID"))
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = get_or_create_request_id(request)
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(RequestValidationError)
async def acvp_request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    if not _is_acvp_v1_request(request):
        return await request_validation_exception_handler(request, exc)
    return acvp_error_response(
        status_code=400,
        code="INVALID_REQUEST",
        message="Request validation failed.",
        path=request.url.path,
        details={"errors": jsonable_encoder(exc.errors())},
        request=request,
        enveloped=True,
    )


@app.exception_handler(StarletteHTTPException)
async def acvp_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if not _is_acvp_v1_request(request):
        return await http_exception_handler(request, exc)
    status_code = int(exc.status_code)
    if status_code == 404:
        code = "UNKNOWN_ACVP_RESOURCE"
        message = "Unknown ACVP resource."
    elif status_code == 405:
        code = "METHOD_NOT_ALLOWED"
        message = "Method not allowed for this ACVP resource."
    elif 400 <= status_code < 500:
        code = "INVALID_REQUEST"
        message = str(exc.detail) if exc.detail else "Invalid ACVP request."
    else:
        code = "INTERNAL_SERVER_ERROR"
        message = "Internal server error."
    return acvp_error_response(
        status_code=status_code,
        code=code,
        message=message,
        path=request.url.path,
        details={"detail": exc.detail} if exc.detail and status_code not in {404, 405} else None,
        request=request,
        enveloped=True,
    )


@app.exception_handler(Exception)
async def acvp_unhandled_exception_handler(request: Request, exc: Exception):
    if not _is_acvp_v1_request(request):
        raise exc
    return acvp_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Internal server error.",
        path=request.url.path,
        request=request,
        enveloped=True,
    )


def _is_acvp_v1_request(request: Request) -> bool:
    return request.url.path.startswith("/acvp/v1")


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/schema/mldsa/registration")
def validate_mldsa_registration_schema(payload: Any = Body(...)) -> Any:
    try:
        normalized = validate_mldsa_registration(payload)
    except AcvpSchemaError as exc:
        return _schema_error_response(exc)
    return {"ok": True, "type": "registration", "normalized": normalized}


@app.post("/api/schema/mldsa/vector-set")
def validate_mldsa_vector_set_schema(payload: Any = Body(...)) -> Any:
    try:
        normalized = validate_mldsa_vector_set(payload)
    except AcvpSchemaError as exc:
        return _schema_error_response(exc)
    return {"ok": True, "type": "vector-set", "normalized": normalized}


@app.post("/api/schema/mldsa/response")
def validate_mldsa_response_schema(payload: Any = Body(...)) -> Any:
    try:
        normalized = validate_mldsa_response(payload)
    except AcvpSchemaError as exc:
        return _schema_error_response(exc)
    return {"ok": True, "type": "response", "normalized": normalized}


@app.post(
    "/api/oracle/mldsa/keygen",
    response_model=MldsaKeygenResponse,
    deprecated=True,
    summary="Legacy/debug ML-DSA keyGen oracle",
    description=LEGACY_ORACLE_DESCRIPTION,
)
def mldsa_keygen(payload: MldsaKeygenRequest) -> MldsaKeygenResponse:
    try:
        result = keygen_internal(payload.parameterSet, payload.seed)
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MldsaKeygenResponse(
        parameterSet=payload.parameterSet,
        seed=payload.seed.upper(),
        pk=result["pk"],
        sk=result["sk"],
    )


@app.post(
    "/api/oracle/mldsa/keygen/expected-results",
    response_model=MldsaKeygenExpectedResultsResponse,
    deprecated=True,
    summary="Legacy/debug ML-DSA keyGen expectedResults oracle",
    description=LEGACY_ORACLE_DESCRIPTION,
)
def mldsa_keygen_expected_results(
    payload: MldsaKeygenExpectedResultsRequest,
) -> MldsaKeygenExpectedResultsResponse:
    try:
        expected_results = generate_keygen_expected_results_from_prompt(payload.prompt)
    except AcvpSchemaError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MldsaKeygenExpectedResultsResponse(expectedResults=expected_results)


@app.post(
    "/api/oracle/mldsa/expected-results",
    response_model=MldsaExpectedResultsResponse,
    deprecated=True,
    summary="Legacy/debug ML-DSA expectedResults oracle",
    description=LEGACY_ORACLE_DESCRIPTION,
)
def mldsa_expected_results(
    payload: MldsaExpectedResultsRequest,
) -> MldsaExpectedResultsResponse:
    try:
        vector_set = validate_mldsa_vector_set(payload.prompt)
        expected_results = generate_expected_results_from_prompt(payload.prompt)
    except AcvpSchemaError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MldsaExpectedResultsResponse(
        mode=vector_set["mode"],
        expectedResults=expected_results,
    )


@app.post(
    "/api/oracle/mldsa/siggen",
    response_model=MldsaSigGenResponse,
    deprecated=True,
    summary="Legacy/debug ML-DSA sigGen oracle",
    description=LEGACY_ORACLE_DESCRIPTION,
)
def mldsa_siggen(payload: Any = Body(...)) -> MldsaSigGenResponse:
    try:
        request = _parse_siggen_request(payload)
        result = siggen_internal(
            request.parameterSet,
            request.sk,
            request.message,
            mu_hex=request.mu,
            rnd_hex=request.rnd,
            external_mu=request.externalMu,
            deterministic=request.deterministic,
            signature_interface=request.signatureInterface,
            pre_hash=request.preHash,
            context_hex=request.context,
            hash_alg=request.hashAlg,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_validation_error_detail(exc)) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MldsaSigGenResponse(
        parameterSet=request.parameterSet,
        signatureInterface=request.signatureInterface,
        externalMu=request.externalMu,
        deterministic=request.deterministic,
        preHash=request.preHash,
        context=_normalize_optional_hex_for_response(request.context),
        hashAlg=_normalize_optional_text_for_response(request.hashAlg),
        signature=result["signature"],
    )


@app.post(
    "/api/oracle/mldsa/sigver",
    response_model=MldsaSigVerResponse,
    deprecated=True,
    summary="Legacy/debug ML-DSA sigVer oracle",
    description=LEGACY_ORACLE_DESCRIPTION,
)
def mldsa_sigver(payload: Any = Body(...)) -> MldsaSigVerResponse:
    try:
        request = _parse_sigver_request(payload)
        result = sigver_internal(
            request.parameterSet,
            request.pk,
            request.message,
            request.signature,
            mu_hex=request.mu,
            external_mu=request.externalMu,
            signature_interface=request.signatureInterface,
            pre_hash=request.preHash,
            context_hex=request.context,
            hash_alg=request.hashAlg,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_validation_error_detail(exc)) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MldsaSigVerResponse(
        parameterSet=request.parameterSet,
        signatureInterface=request.signatureInterface,
        externalMu=request.externalMu,
        preHash=request.preHash,
        context=_normalize_optional_hex_for_response(request.context),
        hashAlg=_normalize_optional_text_for_response(request.hashAlg),
        testPassed=result["testPassed"],
    )


@app.post("/api/import", response_model=ImportSummary)
def import_bundle(payload: ImportRequest) -> Any:
    try:
        prompt_vs = validate_mldsa_vector_set(payload.prompt)
        mode = prompt_vs.get("mode")
        validate_mldsa_response(payload.expectedResults, expected_mode=mode)
        validate_mldsa_response(payload.response, expected_mode=mode)
        bundle = {
            "prompt": payload.prompt,
            "expectedResults": payload.expectedResults,
            "response": payload.response,
            "label": payload.label,
        }
        return _store_import(bundle)
    except AcvpSchemaError as exc:
        return _schema_error_response(exc)
    except (AcvpParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/generated-keygen", response_model=ImportSummary)
def import_generated_keygen_bundle(payload: GeneratedKeygenImportRequest) -> Any:
    try:
        expected_results = generate_keygen_expected_results_from_prompt(payload.prompt)
        validate_mldsa_response(expected_results, expected_mode="keyGen")
        validate_mldsa_response(payload.response, expected_mode="keyGen")
        bundle = {
            "prompt": payload.prompt,
            "expectedResults": expected_results,
            "response": payload.response,
            "label": payload.label,
            "generatedExpectedResults": True,
        }
        return _store_import(bundle)
    except AcvpSchemaError as exc:
        return _schema_error_response(exc)
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (AcvpParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/generated", response_model=ImportSummary)
def import_generated_mldsa_bundle(payload: GeneratedMldsaImportRequest) -> ImportSummary:
    try:
        return _import_generated_mldsa_bundle(payload)
    except AcvpSchemaError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (AcvpParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/generated-and-validate")
def import_generated_mldsa_bundle_and_validate(
    payload: GeneratedMldsaImportRequest,
) -> Dict[str, Any]:
    try:
        imported = _import_generated_mldsa_bundle(payload)
        bundle = _get_bundle(imported.importId)
        validation_result = validate(bundle)
        report = build_report(imported.importId, validation_result)
        bundle["validationResult"] = validation_result
        bundle["report"] = report
        update_import_validation(imported.importId, validation_result, report)
        _record_import_validation_event(imported.importId, validation_result)
    except AcvpSchemaError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except (AcvpParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "import": _model_to_dict(imported),
        "validationResult": validation_result,
        "report": report,
    }


@app.post("/api/validate")
def validate_import(payload: ValidateRequest) -> Dict[str, Any]:
    bundle = _get_bundle(payload.importId)
    try:
        result = validate(bundle)
    except (AcvpParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    bundle["validationResult"] = result
    bundle["report"] = build_report(payload.importId, result)
    update_import_validation(payload.importId, result, bundle["report"])
    _record_import_validation_event(payload.importId, result)
    return result


@app.get("/api/import/{import_id}")
def get_import(import_id: str) -> Dict[str, Any]:
    bundle = _get_bundle(import_id)
    prompt_vs = normalize_acvp_json(bundle["prompt"])
    expected_vs = normalize_acvp_json(bundle["expectedResults"])
    response_vs = normalize_acvp_json(bundle["response"])
    return {
        "importId": import_id,
        "label": bundle.get("label"),
        "summary": _summarize_bundle(import_id, bundle),
        "prompt": prompt_vs,
        "expectedResults": expected_vs,
        "response": response_vs,
        "validationResult": bundle.get("validationResult"),
    }


@app.get("/api/report/{import_id}")
def get_report(import_id: str) -> Dict[str, Any]:
    bundle = _get_bundle(import_id)
    if bundle.get("report") is None:
        result = validate(bundle)
        bundle["validationResult"] = result
        bundle["report"] = build_report(import_id, result)
        update_import_validation(import_id, result, bundle["report"])
        _record_import_validation_event(import_id, result)
    return bundle["report"]


@app.get("/api/sample-data")
def sample_data() -> Dict[str, Any]:
    return {"samples": list_sample_data()}


@app.post("/api/load-sample", response_model=ImportSummary)
def load_sample_import(payload: LoadSampleRequest) -> ImportSummary:
    try:
        bundle = load_sample(payload.sampleName, payload.responseVariant)
        return _store_import(bundle)
    except (SampleLoaderError, AcvpParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/demo/acvp/test-sessions")
def create_demo_acvp_session(payload: DemoAcvpSessionCreateRequest) -> Dict[str, Any]:
    try:
        prompt_vs = validate_mldsa_vector_set(payload.prompt)
        expected_results = None
        if payload.autoGenerateExpectedResults:
            expected_results = generate_expected_results_from_prompt(payload.prompt)
            validate_mldsa_response(expected_results, expected_mode=prompt_vs["mode"])
    except AcvpSchemaError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    except MldsaOracleInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MldsaOracleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    now = _timestamp()
    session_id = str(uuid4())
    session = {
        "sessionId": session_id,
        "createdAt": now,
        "updatedAt": now,
        "status": "vectorReady" if expected_results is not None else "created",
        "label": payload.label,
        "prompt": payload.prompt,
        "expectedResults": expected_results,
        "response": None,
        "validationResult": None,
        "report": None,
        "importId": None,
        "demoOnly": True,
        "notProductionAcvp": True,
    }
    save_demo_session(session)
    record_state_event(
        "demo_session",
        session_id,
        None,
        session["status"],
        "created",
        details={"reason": "Demo ACVP session created."},
    )
    return _demo_session_summary(session)


@app.get("/api/demo/acvp/test-sessions")
def list_demo_acvp_sessions() -> Dict[str, Any]:
    return {
        "demoOnly": True,
        "notProductionAcvp": True,
        "sessions": [
            _demo_session_summary(session)
            for session in list_demo_session_records()
        ],
    }


@app.get("/api/demo/acvp/test-sessions/{session_id}")
def get_demo_acvp_session(session_id: str) -> Dict[str, Any]:
    return _public_demo_session(_get_demo_session(session_id))


@app.get("/api/demo/acvp/test-sessions/{session_id}/vector-set")
def get_demo_acvp_session_vector_set(session_id: str) -> Dict[str, Any]:
    session = _get_demo_session(session_id)
    return {
        "sessionId": session_id,
        "demoOnly": True,
        "notProductionAcvp": True,
        "prompt": session["prompt"],
    }


@app.post("/api/demo/acvp/test-sessions/{session_id}/responses")
def submit_demo_acvp_session_response(
    session_id: str,
    payload: DemoAcvpResponseSubmitRequest,
) -> Dict[str, Any]:
    session = _get_demo_session(session_id)
    mode = normalize_acvp_json(session["prompt"]).get("mode")
    try:
        validate_mldsa_response(payload.response, expected_mode=mode)
    except AcvpSchemaError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc

    session["response"] = payload.response
    session["updatedAt"] = _timestamp()
    session["status"] = "responseSubmitted"

    validation_result = None
    if payload.validateImmediately:
        validation_result = _validate_demo_session(session)
    else:
        save_demo_session(session)
        record_state_event(
            "demo_session",
            session_id,
            None,
            session["status"],
            "responseSubmitted",
            details={"reason": "Demo response submitted without immediate validation."},
        )

    return {
        "sessionId": session_id,
        "status": session["status"],
        "validationResult": validation_result,
        "demoOnly": True,
        "notProductionAcvp": True,
    }


@app.get("/api/demo/acvp/test-sessions/{session_id}/validation")
def get_demo_acvp_session_validation(session_id: str) -> Dict[str, Any]:
    session = _get_demo_session(session_id)
    if session["response"] is None:
        raise HTTPException(status_code=409, detail="Response has not been submitted")
    if session["validationResult"] is None:
        _validate_demo_session(session)
    return {
        "sessionId": session_id,
        "validationResult": session["validationResult"],
        "demoOnly": True,
        "notProductionAcvp": True,
    }


@app.get("/api/demo/acvp/test-sessions/{session_id}/report")
def get_demo_acvp_session_report(session_id: str) -> Dict[str, Any]:
    session = _get_demo_session(session_id)
    if session["response"] is None:
        raise HTTPException(status_code=409, detail="Response has not been submitted")
    if session["report"] is None:
        _validate_demo_session(session)
    report = dict(session["report"])
    report["sessionId"] = session_id
    report["demoOnly"] = True
    report["notProductionAcvp"] = True
    return report


@app.delete("/api/demo/acvp/test-sessions/{session_id}")
def delete_demo_acvp_session(session_id: str) -> Dict[str, Any]:
    session = _get_demo_session(session_id)
    delete_demo_session_record(session_id)
    record_state_event(
        "demo_session",
        session_id,
        session.get("status"),
        "deleted",
        "deleted",
        details={"reason": "Demo ACVP session deleted."},
    )
    return {
        "deleted": True,
        "sessionId": session_id,
        "demoOnly": True,
        "notProductionAcvp": True,
    }


@app.delete("/api/demo/clear")
def clear_demo_data(confirm: bool = False) -> Dict[str, Any]:
    if not confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to clear local demo data")
    db_path = get_db_path()
    deleted_files = [str(db_path)] if db_path.exists() else []
    reset_db_for_tests()
    return {
        "deleted": True,
        "deletedFiles": deleted_files,
        "message": "Local demo database records and current SQLite file were cleared.",
        "demoOnly": True,
        "notProductionAcvp": True,
    }


def _import_generated_mldsa_bundle(payload: GeneratedMldsaImportRequest) -> ImportSummary:
    prompt_vs = validate_mldsa_vector_set(payload.prompt)
    mode = prompt_vs["mode"]
    expected_results = generate_expected_results_from_prompt(payload.prompt)
    validate_mldsa_response(expected_results, expected_mode=mode)
    validate_mldsa_response(payload.response, expected_mode=mode)
    bundle = {
        "prompt": payload.prompt,
        "expectedResults": expected_results,
        "response": payload.response,
        "label": payload.label,
        "generatedExpectedResults": True,
    }
    return _store_import(bundle)


def _validate_demo_session(session: Dict[str, Any]) -> Dict[str, Any]:
    if session["expectedResults"] is None:
        raise HTTPException(status_code=409, detail="Expected results are not available")
    if session["response"] is None:
        raise HTTPException(status_code=409, detail="Response has not been submitted")

    bundle = {
        "prompt": session["prompt"],
        "expectedResults": session["expectedResults"],
        "response": session["response"],
        "label": session.get("label"),
    }
    validation_result = validate(bundle)
    report = build_report(session["sessionId"], validation_result)
    session["validationResult"] = validation_result
    session["report"] = report
    session["updatedAt"] = _timestamp()
    session["status"] = (
        "validated" if _validation_passed(validation_result) else "failed"
    )
    save_demo_session(session)
    record_state_event(
        "demo_session",
        session["sessionId"],
        "responseSubmitted",
        session["status"],
        "validated" if session["status"] == "validated" else "failed",
        details={"reason": "Demo response validated synchronously."},
    )
    return validation_result


def _validation_passed(validation_result: Dict[str, Any]) -> bool:
    summary = validation_result["summary"]
    return (
        summary["failed"] == 0
        and summary["missing"] == 0
        and summary["malformed"] == 0
        and summary.get("extra", 0) == 0
    )


def _demo_session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    prompt_summary = summarize_vector_set(normalize_acvp_json(session["prompt"]))
    return {
        "sessionId": session["sessionId"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "status": session["status"],
        "label": session.get("label"),
        **prompt_summary,
        "demoOnly": True,
        "notProductionAcvp": True,
    }


def _public_demo_session(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_demo_session_summary(session),
        "prompt": session["prompt"],
        "expectedResults": session["expectedResults"],
        "response": session["response"],
        "validationResult": session["validationResult"],
        "report": session["report"],
        "importId": session["importId"],
    }


def _get_demo_session(session_id: str) -> Dict[str, Any]:
    session = DEMO_SESSION_STORE.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown demo sessionId")
    return session


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_to_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def _store_import(bundle: Dict[str, Any]) -> ImportSummary:
    prompt_vs = normalize_acvp_json(bundle["prompt"])
    normalize_acvp_json(bundle["expectedResults"])
    normalize_acvp_json(bundle["response"])

    import_id = str(uuid4())
    now = _timestamp()
    record = {
        **bundle,
        "importId": import_id,
        "createdAt": now,
        "updatedAt": now,
    }
    save_import_record(record)
    record_state_event(
        "import",
        import_id,
        None,
        "imported",
        "created",
        details={"reason": "Import bundle stored."},
    )
    return _summarize_bundle(import_id, record)


def _summarize_bundle(import_id: str, bundle: Dict[str, Any]) -> ImportSummary:
    prompt_summary = summarize_vector_set(normalize_acvp_json(bundle["prompt"]))
    return ImportSummary(importId=import_id, label=bundle.get("label"), **prompt_summary)


def _get_bundle(import_id: str) -> Dict[str, Any]:
    bundle = get_import_record(import_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Unknown importId")
    return bundle


def _record_import_validation_event(import_id: str, validation_result: Dict[str, Any]) -> None:
    status = "validated" if _validation_passed(validation_result) else "failed"
    record_state_event(
        "import",
        import_id,
        "imported",
        status,
        status,
        details={"summary": validation_result.get("summary", {})},
    )


def _schema_error_response(exc: AcvpSchemaError) -> JSONResponse:
    return JSONResponse(status_code=400, content=exc.to_dict())


def _parse_siggen_request(payload: Any) -> MldsaSigGenRequest:
    if isinstance(payload, MldsaSigGenRequest):
        return payload
    return MldsaSigGenRequest.model_validate(payload)


def _parse_sigver_request(payload: Any) -> MldsaSigVerRequest:
    if isinstance(payload, MldsaSigVerRequest):
        return payload
    return MldsaSigVerRequest.model_validate(payload)


def _validation_error_detail(exc: ValidationError) -> Any:
    try:
        return exc.errors(include_context=False)
    except TypeError:
        return exc.errors()


def _normalize_optional_hex_for_response(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.upper()


def _normalize_optional_text_for_response(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.upper()
