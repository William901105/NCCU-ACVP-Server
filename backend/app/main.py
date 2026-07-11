from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .acvp_core.bootstrap import build_algorithm_registry
from .acvp_protocol.errors import acvp_error_response
from .acvp_protocol.request_context import get_or_create_request_id, reset_request_id, set_request_id
from .acvp_protocol.routes import router as acvp_v1_router
from .storage.sqlite_store import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = build_algorithm_registry()
    if len(registry) == 0:
        raise RuntimeError("At least one algorithm module must be registered.")
    app.state.algorithm_registry = registry
    init_db()
    yield


app = FastAPI(
    title="NCCU ACVP Server | FIPS 204 / ML-DSA",
    version="0.1.0",
    description="NCCU ACVP Server strict ML-DSA ACVP workflow using NIST GenVal.",
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


@app.middleware("http")
async def acvp_request_id_middleware(request: Request, call_next):
    token = set_request_id(request.headers.get("X-Request-ID"))
    try:
        if request.url.path.startswith("/acvp/v1"):
            if "workflowProfile" in request.query_params:
                return acvp_error_response(
                    status_code=400,
                    code="WORKFLOW_PROFILE_NOT_SUPPORTED",
                    message="workflowProfile is not supported. NCCU ACVP Server uses strict workflow only.",
                    path="$.workflowProfile",
                    request=request,
                    enveloped=True,
                )
            if "generationProfile" in request.query_params:
                return acvp_error_response(
                    status_code=400,
                    code="GENERATION_PROFILE_NOT_SUPPORTED",
                    message="generationProfile is not supported. NCCU ACVP Server uses NIST GenVal only.",
                    path="$.generationProfile",
                    request=request,
                    enveloped=True,
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = get_or_create_request_id(request)
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(RequestValidationError)
async def acvp_request_validation_exception_handler(request: Request, exc: RequestValidationError):
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
        code, message = "UNKNOWN_ACVP_RESOURCE", "Unknown ACVP resource."
    elif status_code == 405:
        code, message = "METHOD_NOT_ALLOWED", "Method not allowed for this ACVP resource."
    elif 400 <= status_code < 500:
        code, message = "INVALID_REQUEST", str(exc.detail) if exc.detail else "Invalid ACVP request."
    else:
        code, message = "INTERNAL_SERVER_ERROR", "Internal server error."
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
