from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi.responses import JSONResponse

from ..acvp_core.algorithm_identity import AlgorithmIdentity
from ..acvp_core.algorithm_module import AcvpAlgorithmModule, normalize_module_validation
from ..acvp_core.registry import AlgorithmModuleRegistry, ModuleNotFoundError
from ..acvp_core.schema_error import AcvpSchemaError
from ..acvp_parser import AcvpParseError, normalize_acvp_json, summarize_vector_set
from ..genval import (
    GenValArtifactError,
    GenValConfigurationError,
    GenValExecutionError,
    NistCliGenValProvider,
    get_genval_settings,
)
from ..genval.artifacts import vector_set_artifact_dir
from ..models import (
    AcvpV1TestSessionCertificationRequest,
    AcvpV1TestSessionCreateRequest,
    AcvpV1VectorSetGenerateRequest,
)
from ..storage.store import (
    ACVP_SKELETON_SESSION_STORE,
    ACVP_SKELETON_VECTOR_SET_STORE,
    create_acvp_request,
    delete_acvp_vector_sets_for_session,
    get_acvp_session,
    get_acvp_request,
    get_acvp_request_for_session,
    get_acvp_vector_set,
    get_acvp_vector_set_by_vs_id,
    list_acvp_sessions,
    list_acvp_vector_sets_for_session,
    save_acvp_request,
    save_acvp_session,
    save_acvp_vector_set,
)
from .disposition import build_acvp_vector_set_results
from .errors import acvp_error_response
from .paging import apply_paging, build_paged_body
from .state_machine import (
    StateTransitionError,
    TestSessionStatus,
    VectorSetStatus,
    add_state_event,
    is_terminal_status,
    now_timestamp,
    session_is_expired,
    transition_session,
    transition_vector_set,
    vector_set_is_expired,
)
from .envelope import EXECUTION_BACKEND, WORKFLOW_POLICY

NIST_GENVAL_PROVIDER_ID = "nist-genval"
NIST_GENVAL_PROVIDER_NAME = "NIST ACVP-Server GenValAppRunner"
SERVER_METADATA: Dict[str, Any] = {
    "workflowPolicy": WORKFLOW_POLICY,
    "executionBackend": EXECUTION_BACKEND,
}

NIST_REFERENCES = [
    "https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html",
]

_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
VECTOR_GENERATION_AVAILABLE_ACTION = (
    "NIST GenVal vector generation is available from the registered capabilities."
)


def with_server_metadata(body: Dict[str, Any]) -> Dict[str, Any]:
    return {**body, **SERVER_METADATA}


def acvp_error(
    status_code: int,
    code: str,
    message: str,
    path: Optional[str] = None,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    return acvp_error_response(
        status_code=status_code,
        code=code,
        message=message,
        path=path,
        details=details,
    )


def version() -> Dict[str, Any]:
    return with_server_metadata(
        {
            "acvVersion": "1.0",
            "apiVersion": "v1",
            "serverName": "NCCU ACVP Server",
            "workflowPolicy": WORKFLOW_POLICY,
            "executionBackend": EXECUTION_BACKEND,
            "nistReferences": NIST_REFERENCES,
        }
    )


def algorithms(registry: AlgorithmModuleRegistry) -> Dict[str, Any]:
    return with_server_metadata(
        {"algorithms": registry.list_descriptors()}
    )


def _validate_registration_container_with_modules(
    payload: Any,
    registry: AlgorithmModuleRegistry,
) -> Dict[str, Any]:
    obj = _require_json_object(payload, "$")
    algorithms_value = _require_json_field(obj, "algorithms", "$")
    algorithms = _require_json_array(algorithms_value, "$.algorithms", non_empty=True)

    normalized_algorithms: List[Dict[str, Any]] = []
    seen = set()

    for index, item in enumerate(algorithms):
        item_path = _child_path("$.algorithms", index)
        registration = _require_json_object(item, item_path)
        algorithm = _require_json_string(
            _require_json_field(registration, "algorithm", item_path),
            _child_path(item_path, "algorithm"),
        )
        mode = _require_json_string(
            _require_json_field(registration, "mode", item_path),
            _child_path(item_path, "mode"),
        )
        revision = _require_json_string(
            _require_json_field(registration, "revision", item_path),
            _child_path(item_path, "revision"),
        )
        module = _module_for_identity(registry, algorithm, mode, revision, item_path)
        try:
            normalized = module.validate_registration(registration)
        except AcvpSchemaError as exc:
            raise _with_prefixed_path(exc, item_path) from exc

        normalized_algorithm = str(normalized.get("algorithm"))
        normalized_mode = str(normalized.get("mode"))
        normalized_revision = str(normalized.get("revision"))
        normalized_identity = AlgorithmIdentity(
            normalized_algorithm,
            normalized_mode,
            normalized_revision,
        )
        if not module.supports(normalized_identity):
            raise _module_not_found_schema_error(
                registry,
                ModuleNotFoundError(normalized_identity),
                item_path,
            )

        if normalized_identity in seen:
            raise AcvpSchemaError(
                "duplicate_registration",
                "Duplicate algorithm/mode/revision registration.",
                _child_path(item_path, "mode"),
            )
        seen.add(normalized_identity)
        normalized_algorithms.append(normalized)

    container: Dict[str, Any] = {"algorithms": normalized_algorithms}
    if "label" in obj:
        container["label"] = _require_json_string(obj["label"], "$.label")
    if "metadata" in obj:
        metadata = obj["metadata"]
        if not isinstance(metadata, (dict, list)):
            raise AcvpSchemaError(
                "invalid_type",
                "metadata must be a JSON object or array when provided",
                "$.metadata",
            )
        container["metadata"] = metadata
    return container


def _negotiate_capabilities_with_modules(
    container: Dict[str, Any],
    registry: AlgorithmModuleRegistry,
) -> Dict[str, Any]:
    negotiated: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    identities: List[tuple[str, str]] = []

    for index, registration in enumerate(container["algorithms"]):
        item_path = _child_path("$.algorithms", index)
        algorithm = str(registration["algorithm"])
        mode = str(registration["mode"])
        revision = str(registration["revision"])
        module = _module_for_identity(registry, algorithm, mode, revision, item_path)
        if (algorithm, revision) not in identities:
            identities.append((algorithm, revision))
        try:
            result = module.negotiate_capabilities(registration)
        except AcvpSchemaError as exc:
            raise _with_prefixed_path(exc, item_path) from exc

        for entry in result.get("negotiated", []):
            negotiated_entry = dict(entry)
            negotiated_entry.setdefault("algorithm", algorithm)
            negotiated_entry.setdefault("revision", revision)
            negotiated.append(negotiated_entry)
        unsupported.extend(result.get("unsupported", []))
        warnings.extend(result.get("warnings", []))

    if not negotiated:
        raise AcvpSchemaError(
            "UNSUPPORTED_CAPABILITIES",
            "No supported capabilities were negotiated.",
            "$.algorithms",
        )

    algorithm_values = [identity[0] for identity in identities]
    revision_values = [identity[1] for identity in identities]
    return {
        "algorithm": algorithm_values[0] if len(algorithm_values) == 1 else algorithm_values,
        "revision": revision_values[0] if len(revision_values) == 1 else revision_values,
        "negotiated": negotiated,
        "unsupported": unsupported,
        "warnings": warnings,
        "nextAction": VECTOR_GENERATION_AVAILABLE_ACTION,
    }


def _module_for_prompt(
    prompt: Any,
    registry: AlgorithmModuleRegistry,
) -> AcvpAlgorithmModule:
    try:
        vector_set = normalize_acvp_json(prompt)
    except AcvpParseError as exc:
        raise AcvpSchemaError("invalid_container", str(exc), "$") from exc
    algorithm = _require_json_string(
        _require_json_field(vector_set, "algorithm", "$"),
        "$.algorithm",
    )
    mode = _require_json_string(
        _require_json_field(vector_set, "mode", "$"),
        "$.mode",
    )
    revision = _require_json_string(
        _require_json_field(vector_set, "revision", "$"),
        "$.revision",
    )
    return _module_for_identity(registry, algorithm, mode, revision, "$")


def _module_for_identity(
    registry: AlgorithmModuleRegistry,
    algorithm: str,
    mode: str,
    revision: str,
    path: str,
) -> AcvpAlgorithmModule:
    identity = AlgorithmIdentity(algorithm, mode, revision)
    try:
        return registry.get_module(identity)
    except ModuleNotFoundError as exc:
        raise _module_not_found_schema_error(registry, exc, path) from exc


def _module_not_found_schema_error(
    registry: AlgorithmModuleRegistry,
    exc: ModuleNotFoundError,
    path: str,
) -> AcvpSchemaError:
    identity = exc.identity
    identities = registry.identities()
    algorithm_identities = tuple(
        item for item in identities if item.algorithm == identity.algorithm
    )
    if not algorithm_identities:
        return AcvpSchemaError(
            "unsupported_algorithm",
            f"Unsupported algorithm module: {identity.algorithm}",
            _child_path(path, "algorithm"),
        )

    supported_modes = {item.mode for item in algorithm_identities}
    supported_revisions = {item.revision for item in algorithm_identities}
    if identity.mode not in supported_modes:
        return AcvpSchemaError(
            "invalid_mode",
            f"Unsupported mode for {identity.algorithm}: {identity.mode}",
            _child_path(path, "mode"),
        )
    if identity.revision not in supported_revisions:
        return AcvpSchemaError(
            "unsupported_revision",
            f"Unsupported revision for {identity.algorithm}: {identity.revision}",
            _child_path(path, "revision"),
        )
    return AcvpSchemaError(
        "unsupported_mode_revision_combination",
        (
            f"Unsupported mode/revision combination for {identity.algorithm}: "
            f"{identity.mode}/{identity.revision}"
        ),
        _child_path(path, "revision"),
    )


def _require_json_object(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AcvpSchemaError("invalid_type", "Expected object", path)
    return value


def _require_json_array(value: Any, path: str, *, non_empty: bool = False) -> List[Any]:
    if not isinstance(value, list):
        raise AcvpSchemaError("invalid_type", "Expected array", path)
    if non_empty and not value:
        raise AcvpSchemaError("invalid_value", "Array must not be empty", path)
    return value


def _require_json_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise AcvpSchemaError("invalid_type", "Expected string", path)
    return value


def _require_json_field(obj: Dict[str, Any], field: str, path: str) -> Any:
    if field not in obj:
        raise AcvpSchemaError(
            "missing_required_field",
            f"Missing required field: {field}",
            _child_path(path, field),
        )
    return obj[field]


def _child_path(path: str, child: object) -> str:
    if isinstance(child, int):
        return f"{path}[{child}]"
    return f"{path}.{child}" if path else f"$.{child}"


def _with_prefixed_path(exc: AcvpSchemaError, prefix: str) -> AcvpSchemaError:
    if not exc.path or exc.path == "$":
        path = prefix
    elif exc.path.startswith("$."):
        path = f"{prefix}{exc.path[1:]}"
    else:
        path = exc.path
    return AcvpSchemaError(exc.code, exc.message, path)


def list_test_sessions(
    status: Optional[str] = None,
    *,
    limit: int,
    offset: int,
) -> Any:
    status_error = _validate_status_filter(
        status,
        allowed={item.value for item in TestSessionStatus},
        entity="test session",
    )
    if isinstance(status_error, JSONResponse):
        return status_error

    sessions = list_acvp_sessions(status=status)
    items = [_session_summary(session) for session in sessions]
    page, pagination = apply_paging(items, limit=limit, offset=offset)
    body = build_paged_body(
        items=page,
        key="testSessions",
        limit=limit,
        offset=offset,
        total=pagination["total"],
        resource_path="/acvp/v1/testSessions",
        query={"status": status},
    )
    body["query"] = {"status": status} if status is not None else {}
    return with_server_metadata(
        body
    )


def create_test_session(
    payload: AcvpV1TestSessionCreateRequest,
    registry: AlgorithmModuleRegistry,
) -> Any:
    """Create a strict registration session; prompt sessions are intentionally absent."""
    try:
        container_payload: Dict[str, Any] = {"algorithms": payload.algorithms}
        if payload.label is not None:
            container_payload["label"] = payload.label
        if payload.metadata is not None:
            container_payload["metadata"] = payload.metadata
        registration_container = _validate_registration_container_with_modules(
            container_payload,
            registry,
        )
        negotiated_capabilities = _negotiate_capabilities_with_modules(
            registration_container,
            registry,
        )
        campaign_seed = _resolve_campaign_seed(
            payload.campaignSeed,
            registration_container,
        )
        tests_per_group = _resolve_tests_per_group(
            payload.testsPerGroup,
        )
    except AcvpSchemaError as exc:
        return acvp_error(400, exc.code, exc.message, exc.path)

    now = _timestamp()
    session_id = str(uuid4())
    expires_at = _expires_at_from_seconds(payload.expiresInSeconds)
    is_sample = _resolve_is_sample(payload.isSample)
    session = {
        "testSessionId": session_id,
        "createdAt": now,
        "updatedAt": now,
        "status": TestSessionStatus.CREATED.value,
        "label": payload.label,
        "expiresAt": expires_at,
        "registration": registration_container,
        "negotiatedCapabilities": negotiated_capabilities,
        "negotiationWarnings": negotiated_capabilities["warnings"],
        "unsupported": negotiated_capabilities["unsupported"],
        "campaignSeed": campaign_seed,
        "testsPerGroup": tests_per_group,
        "isSample": is_sample,
        "vectorSetIds": [],
        "vectorSetUrls": [],
        "nextAction": VECTOR_GENERATION_AVAILABLE_ACTION,
        **SERVER_METADATA,
    }
    _record_created(session, TestSessionStatus.CREATED.value, "Registration test session created.")
    transition_session(
        session,
        TestSessionStatus.CAPABILITIES_ACCEPTED.value,
        reason="Capabilities accepted for strict NIST GenVal execution.",
    )
    save_acvp_session(session)

    if payload.autoGenerateVectorSets:
        generated = _generate_and_store_vector_sets(
            session,
            registry=registry,
            campaign_seed=campaign_seed,
            tests_per_group=tests_per_group,
            expires_at=expires_at,
            is_sample=is_sample,
            reason="Registration requested autoGenerateVectorSets.",
        )
        if isinstance(generated, JSONResponse):
            delete_acvp_vector_sets_for_session(session_id)
            ACVP_SKELETON_SESSION_STORE.pop(session_id, None)
            return generated
        return _registration_session_response(session)

    return _registration_session_response(session)


def request_nist_vector_sets_for_session(
    session_id: str,
    payload: AcvpV1VectorSetGenerateRequest,
    registry: AlgorithmModuleRegistry,
) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}/vectorSets/generate"
    legacy = _reject_legacy_local_session(session, path)
    if isinstance(legacy, JSONResponse):
        return legacy
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if "negotiatedCapabilities" not in session:
        return acvp_error(
            409,
            "NEGOTIATED_CAPABILITIES_NOT_AVAILABLE",
            "This test session was not created from a registration container.",
            path,
        )
    if session["vectorSetIds"]:
        return acvp_error(
            409,
            "VECTOR_SETS_ALREADY_GENERATED",
            "Vector sets have already been generated for this test session.",
            path,
        )
    if session["status"] != TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return acvp_error(
            409,
            "INVALID_SESSION_STATE",
            "Vector sets can only be generated for a capabilitiesAccepted session.",
            path,
        )

    try:
        campaign_seed = _resolve_campaign_seed(
            payload.campaignSeed if payload.campaignSeed is not None else session.get("campaignSeed"),
            session["registration"],
        )
        tests_per_group = _resolve_tests_per_group(
            payload.testsPerGroup if payload.testsPerGroup is not None else session.get("testsPerGroup"),
        )
    except AcvpSchemaError as exc:
        return acvp_error(400, exc.code, exc.message, exc.path)

    generated = _generate_and_store_vector_sets(
        session,
        registry=registry,
        campaign_seed=campaign_seed,
        tests_per_group=tests_per_group,
        expires_at=_expires_at_from_seconds(payload.expiresInSeconds) or session.get("expiresAt"),
        is_sample=_vector_set_session_is_sample(session),
        reason="Explicit vector generation endpoint called.",
    )
    if isinstance(generated, JSONResponse):
        return generated
    return _registration_session_response(session)


def _registration_session_response(session: Dict[str, Any]) -> Dict[str, Any]:
    vector_sets = _session_vector_sets(session)
    vs_ids = [int(vector_set["vsId"]) for vector_set in vector_sets]
    vector_set_urls = [
        _nested_vector_set_path(session["testSessionId"], vs_id)
        for vs_id in vs_ids
    ]
    result_summary = _session_result_summary(session)
    response = {
        "testSessionId": session["testSessionId"],
        "status": session["status"],
        "label": session.get("label"),
        "negotiatedCapabilities": session["negotiatedCapabilities"],
        "negotiationWarnings": session["negotiationWarnings"],
        "unsupported": session["unsupported"],
        "vectorSetIds": vs_ids,
        "vsIds": vs_ids,
        "vectorSetUrls": vector_set_urls,
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "expiresAt": session.get("expiresAt"),
        "campaignSeed": session.get("campaignSeed"),
        "testsPerGroup": session.get("testsPerGroup"),
        "isSample": session.get("isSample"),
        "passed": result_summary["sessionPassed"],
        "publishable": result_summary["sessionPassed"],
        "stateHistory": _public_state_history(session.get("stateHistory", [])),
    }
    if "vectorGeneration" in session:
        response["vectorGeneration"] = session["vectorGeneration"]
    else:
        response["nextAction"] = VECTOR_GENERATION_AVAILABLE_ACTION
    return with_server_metadata(response)


def legacy_python_session_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve pre-Stage 7 internal IDs for direct, non-HTTP handler callers."""
    session_id = response.get("testSessionId")
    session = get_acvp_session(str(session_id)) if session_id is not None else None
    if session is None:
        return response
    legacy = dict(response)
    internal_ids = list(session.get("vectorSetIds", []))
    legacy["vectorSetIds"] = internal_ids
    legacy["vectorSetUrls"] = [
        f"/acvp/v1/testSessions/{session_id}/vectorSets/{vector_set_id}"
        for vector_set_id in internal_ids
    ]
    return legacy


def _generate_and_store_vector_sets(
    session: Dict[str, Any],
    *,
    registry: AlgorithmModuleRegistry,
    campaign_seed: str,
    tests_per_group: int,
    expires_at: Optional[str],
    is_sample: bool,
    reason: str,
) -> Optional[JSONResponse]:
    try:
        prepared = _prepare_nist_generated_vector_sets(
            session,
            registry=registry,
            campaign_seed=campaign_seed,
            is_sample=is_sample,
        )
    except AcvpSchemaError as exc:
        return acvp_error(500, exc.code, exc.message, exc.path)
    except GenValConfigurationError:
        return acvp_error(
            500,
            "NIST_GENVAL_NOT_READY",
            "NIST GenVal is not configured or built.",
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValArtifactError:
        return acvp_error(
            500,
            "NIST_GENVAL_ARTIFACT_MISSING",
            "A required NIST GenVal artifact is unavailable.",
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValExecutionError:
        return acvp_error(
            500,
            "NIST_GENVAL_EXECUTION_ERROR",
            "NIST GenVal execution failed.",
            "$",
            details=_nist_genval_error_details(),
        )
    except ValueError as exc:
        return acvp_error(500, "VECTOR_GENERATION_ERROR", str(exc), "$")

    vector_set_ids: List[str] = []
    vector_set_urls: List[str] = []
    now = _timestamp()
    for vector_set in prepared:
        vector_set["createdAt"] = now
        vector_set["updatedAt"] = now
        vector_set["expiresAt"] = expires_at
        _record_created(
            vector_set,
            VectorSetStatus.CREATED.value,
            "Vector set created from negotiated capabilities.",
        )
        transition_vector_set(
            vector_set,
            VectorSetStatus.READY.value,
            reason="NIST GenVal generated the vector set.",
            metadata={"executionBackend": EXECUTION_BACKEND},
        )
        save_acvp_vector_set(vector_set)
        vector_set_ids.append(vector_set["vectorSetId"])
        vector_set_urls.append(
            _nested_vector_set_path(session["testSessionId"], int(vector_set["vsId"]))
        )

    if expires_at is not None and session.get("expiresAt") is None:
        session["expiresAt"] = expires_at
    transition_session(
        session,
        TestSessionStatus.VECTOR_READY.value,
        reason=reason,
        metadata={"generatedVectorSetCount": len(vector_set_ids)},
    )
    add_state_event(
        session,
        event="vectorGenerated",
        from_status=session["status"],
        to_status=session["status"],
        reason="Vector sets generated from negotiated capabilities.",
        metadata={
            "campaignSeed": campaign_seed,
            "testsPerGroup": tests_per_group,
            "generatedVectorSetCount": len(vector_set_ids),
            "provider": NIST_GENVAL_PROVIDER_ID,
        },
    )
    session["campaignSeed"] = campaign_seed
    session["testsPerGroup"] = tests_per_group
    session["vectorSetIds"] = vector_set_ids
    session["vectorSetUrls"] = vector_set_urls
    session["nextAction"] = "Download vector sets and submit results."
    session["vectorGeneration"] = {
        "campaignSeed": campaign_seed,
        "testsPerGroup": tests_per_group,
        "generatedVectorSetCount": len(vector_set_ids),
        "modes": [
            normalize_acvp_json(vector_set["prompt"])["mode"]
            for vector_set in prepared
        ],
        "provider": NIST_GENVAL_PROVIDER_ID,
        "providerName": NIST_GENVAL_PROVIDER_NAME,
        "executionBackend": EXECUTION_BACKEND,
    }
    save_acvp_session(session)
    return None


def _prepare_nist_generated_vector_sets(
    session: Dict[str, Any],
    *,
    registry: AlgorithmModuleRegistry,
    campaign_seed: str,
    is_sample: bool,
) -> List[Dict[str, Any]]:
    settings = get_genval_settings()
    genval_provider = NistCliGenValProvider(settings)
    source_commit = _nist_source_commit(settings.project_root)
    nist_registrations = _map_registrations_to_nist(
        session["registration"],
        registry,
        is_sample=is_sample,
    )

    prepared: List[Dict[str, Any]] = []
    for nist_registration in nist_registrations:
        vector_set_id = str(uuid4())
        work_dir = vector_set_artifact_dir(
            settings.artifact_root,
            session["testSessionId"],
            vector_set_id,
        )
        genval_provider.check_registration(nist_registration, work_dir)
        artifacts = genval_provider.generate(nist_registration, work_dir)
        if artifacts.expected_results is None:
            raise GenValArtifactError(
                f"NIST GenVal did not produce expectedResults.json in {work_dir}"
            )

        prompt = _payload_with_is_sample(_read_json_file(artifacts.prompt), is_sample)
        expected_results = _read_json_file(artifacts.expected_results)
        module = _module_for_prompt(prompt, registry)
        prompt_vs = module.validate_prompt(prompt)
        module.validate_response(expected_results, expected_mode=prompt_vs["mode"])

        prepared.append(
            {
                "vectorSetId": vector_set_id,
                "testSessionId": session["testSessionId"],
                "status": VectorSetStatus.CREATED.value,
                "prompt": prompt,
                "expectedResults": expected_results,
                "response": None,
                "validationResult": None,
                "report": None,
                "generatedFromCapabilities": True,
                "mode": prompt_vs["mode"],
                "vsId": prompt_vs["vsId"],
                "campaignSeed": campaign_seed,
                "isSample": is_sample,
                "provider": NIST_GENVAL_PROVIDER_ID,
                "providerName": NIST_GENVAL_PROVIDER_NAME,
                "expectedResultsDebugOnly": True,
                "hasInternalProjection": True,
                "nistSourceCommit": source_commit,
                "artifactPaths": _genval_artifact_paths(work_dir, artifacts),
                **SERVER_METADATA,
            }
        )
    return prepared


def _map_registrations_to_nist(
    registration_container: Dict[str, Any],
    registry: AlgorithmModuleRegistry,
    *,
    is_sample: bool,
) -> List[Dict[str, Any]]:
    registrations = _require_json_array(
        registration_container.get("algorithms"),
        "$.algorithms",
        non_empty=True,
    )
    mapped: List[Dict[str, Any]] = []
    for index, value in enumerate(registrations):
        path = _child_path("$.algorithms", index)
        registration = _require_json_object(value, path)
        module = _module_for_identity(
            registry,
            _require_json_string(registration.get("algorithm"), _child_path(path, "algorithm")),
            _require_json_string(registration.get("mode"), _child_path(path, "mode")),
            _require_json_string(registration.get("revision"), _child_path(path, "revision")),
            path,
        )
        normalized = module.validate_registration(registration)
        mapped.append(
            module.to_nist_registration(
                normalized,
                vs_id=index + 1,
                is_sample=is_sample,
            )
        )

    return mapped


def _genval_artifact_paths(work_dir: Path, artifacts: Any) -> Dict[str, str]:
    paths = {
        "root": str(work_dir),
        "registration": str(artifacts.registration),
        "prompt": str(artifacts.prompt),
        "internalProjection": str(artifacts.internal_projection),
        "checkStdout": str(work_dir / "check.stdout.txt"),
        "checkStderr": str(work_dir / "check.stderr.txt"),
    }
    if artifacts.expected_results is not None:
        paths["expectedResults"] = str(artifacts.expected_results)
    if artifacts.stdout is not None:
        paths["generationStdout"] = str(artifacts.stdout)
    if artifacts.stderr is not None:
        paths["generationStderr"] = str(artifacts.stderr)
    return paths


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GenValArtifactError(f"Required NIST GenVal artifact is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GenValArtifactError(f"NIST GenVal artifact is not valid JSON: {path}") from exc


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _nist_source_commit(project_root: Path) -> Optional[str]:
    source_path = project_root / "third_party" / "nist-acvp-server" / "NIST_SOURCE.md"
    if not source_path.exists():
        return None
    for line in source_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- source git commit:"):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


def _nist_genval_error_details() -> Dict[str, Any]:
    return {
        "provider": NIST_GENVAL_PROVIDER_ID,
        "providerName": NIST_GENVAL_PROVIDER_NAME,
        "buildCommand": "scripts/nist/build_nist_genval.sh",
        "orleansCommand": "scripts/nist/start_orleans.sh",
    }


def _resolve_campaign_seed(
    provided_seed: Optional[str],
    registration_container: Dict[str, Any],
) -> str:
    if provided_seed is None:
        canonical = json.dumps(registration_container, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
    if not isinstance(provided_seed, str):
        raise AcvpSchemaError("invalid_type", "campaignSeed must be a hex string", "$.campaignSeed")
    if len(provided_seed) % 2 != 0 or _HEX_RE.fullmatch(provided_seed) is None:
        raise AcvpSchemaError("invalid_hex", "campaignSeed must be an even-length hex string", "$.campaignSeed")
    byte_len = len(provided_seed) // 2
    if byte_len < 16 or byte_len > 64:
        raise AcvpSchemaError(
            "invalid_value",
            "campaignSeed must be between 16 and 64 bytes",
            "$.campaignSeed",
        )
    return provided_seed.upper()


def _resolve_tests_per_group(value: Optional[int]) -> int:
    if value is None:
        return 1
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
        raise AcvpSchemaError(
            "invalid_value",
            "testsPerGroup must be an integer between 1 and 10.",
            "$.testsPerGroup",
        )
    return value


def _resolve_is_sample(value: Optional[bool]) -> bool:
    return bool(value) if value is not None else False


def _payload_with_is_sample(payload: Any, is_sample: bool) -> Any:
    if isinstance(payload, dict):
        result = dict(payload)
        result["isSample"] = is_sample
        return result
    if isinstance(payload, list):
        result = []
        applied = False
        for item in payload:
            if isinstance(item, dict) and not applied and (
                "testGroups" in item
                or {"vsId", "algorithm", "mode", "revision"}.intersection(item)
            ):
                updated = dict(item)
                updated["isSample"] = is_sample
                result.append(updated)
                applied = True
            else:
                result.append(item)
        return result
    return payload


def _vector_set_is_sample(vector_set: Dict[str, Any]) -> bool:
    if isinstance(vector_set.get("isSample"), bool):
        return bool(vector_set["isSample"])
    try:
        prompt = normalize_acvp_json(vector_set.get("prompt"))
    except Exception:
        prompt = {}
    value = prompt.get("isSample")
    return bool(value) if isinstance(value, bool) else True


def _vector_set_session_is_sample(session: Dict[str, Any]) -> bool:
    value = session.get("isSample")
    return bool(value) if isinstance(value, bool) else True


def get_test_session(session_id: str) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    _expire_session_if_needed(session)

    return with_server_metadata(
        {
            **_session_summary(session),
            "vectorSets": [
                _vector_set_summary(vector_set)
                for vector_set in _session_vector_sets(session)
            ],
        }
    )


def get_test_session_vector_sets(
    session_id: str,
    status: Optional[str] = None,
    *,
    limit: int,
    offset: int,
) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    _expire_session_if_needed(session)

    status_error = _validate_status_filter(
        status,
        allowed={item.value for item in VectorSetStatus},
        entity="vector set",
    )
    if isinstance(status_error, JSONResponse):
        return status_error

    summaries = [
        _vector_set_summary(vector_set)
        for vector_set in _session_vector_sets(session)
    ]
    if status is not None:
        summaries = [
            summary
            for summary in summaries
            if summary["status"] == status
        ]
    page, pagination = apply_paging(summaries, limit=limit, offset=offset)
    vector_set_urls = [summary["url"] for summary in page]
    body = build_paged_body(
        items=vector_set_urls,
        key="vectorSetUrls",
        limit=limit,
        offset=offset,
        total=pagination["total"],
        resource_path=f"/acvp/v1/testSessions/{session_id}/vectorSets",
        query={"status": status},
    )
    body["testSessionId"] = session_id
    body["vectorSets"] = page
    body["query"] = {"status": status} if status is not None else {}
    if not session["vectorSetIds"] and session["status"] == "capabilitiesAccepted":
        body["nextAction"] = VECTOR_GENERATION_AVAILABLE_ACTION
    return with_server_metadata(body)


def get_vector_set(vector_set_id: str) -> Any:
    vector_set = get_vector_set_or_404(vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    path = f"/acvp/v1/vectorSets/{vector_set_id}"
    return _get_vector_set_prompt_response(vector_set, path)


def get_vector_set_prompt(session_id: str, vs_id: Any) -> Any:
    vector_set = get_vector_set_for_session_or_404(session_id, vs_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    return _get_vector_set_prompt_response(
        vector_set,
        _nested_vector_set_path(session_id, int(vector_set["vsId"])),
    )


def _get_vector_set_prompt_response(vector_set: Dict[str, Any], path: str) -> Any:
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if vector_set["status"] == VectorSetStatus.CREATED.value:
        return acvp_error(
            409,
            "VECTOR_SET_NOT_READY",
            "Vector set is not ready for download.",
            path,
        )

    if vector_set["status"] == VectorSetStatus.READY.value:
        transition_vector_set(
            vector_set,
            VectorSetStatus.DOWNLOADED.value,
            reason="Vector set prompt downloaded.",
        )
        vector_set["downloadedAt"] = vector_set["updatedAt"]
        save_acvp_vector_set(vector_set)
        _mark_session_downloaded_if_complete(vector_set["testSessionId"])

    return vector_set["prompt"]


def get_vector_set_expected_results(vector_set_id: str) -> Any:
    vector_set = get_vector_set_or_404(vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    path = f"/acvp/v1/vectorSets/{vector_set_id}/expectedResults"
    return _get_vector_set_expected_response(
        vector_set, path,
    )


def get_vector_set_expected(session_id: str, vs_id: Any) -> Any:
    vector_set = get_vector_set_for_session_or_404(session_id, vs_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    return _get_vector_set_expected_response(
        vector_set,
        f"{_nested_vector_set_path(session_id, int(vector_set['vsId']))}/expected",
    )


def _get_vector_set_expected_response(vector_set: Dict[str, Any], path: str) -> Any:
    session = get_acvp_session(vector_set["testSessionId"])
    if session is not None:
        legacy = _reject_legacy_local_session(session, path)
        if isinstance(legacy, JSONResponse):
            return legacy
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if vector_set["expectedResults"] is None:
        return acvp_error(
            409,
            "EXPECTED_RESULTS_NOT_READY",
            "Expected results are not available for this vector set.",
            path,
        )

    if not _vector_set_is_sample(vector_set):
        return acvp_error(
            403,
            "EXPECTED_RESULTS_NOT_AVAILABLE",
            "Expected results are not downloadable for non-sample vector sets.",
            path,
        )
    return vector_set["expectedResults"]


def submit_vector_set_results(
    session_id: Optional[str],
    vector_set_id: Any,
    response: Any,
    registry: AlgorithmModuleRegistry,
    *,
    show_expected: bool = False,
    update: bool = False,
) -> Any:
    legacy_direct_identity = (
        session_id is not None
        and isinstance(vector_set_id, str)
        and not vector_set_id.isdigit()
    )
    if session_id is None:
        vector_set = get_vector_set_or_404(vector_set_id)
        path = f"/acvp/v1/vectorSets/{vector_set_id}/results"
    else:
        vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    if session_id is not None:
        path = f"{_nested_vector_set_path(session_id, int(vector_set['vsId']))}/results"
    session = get_acvp_session(vector_set["testSessionId"])
    if session is not None:
        legacy = _reject_legacy_local_session(session, path)
        if isinstance(legacy, JSONResponse):
            return legacy
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if vector_set["status"] not in {
        VectorSetStatus.READY.value,
        VectorSetStatus.DOWNLOADED.value,
        VectorSetStatus.RESULTS_SUBMITTED.value,
        VectorSetStatus.VALIDATED.value,
        VectorSetStatus.FAILED.value,
    }:
        return acvp_error(
            409,
            "VECTOR_SET_NOT_READY",
            "Vector set is not ready for result submission.",
            path,
        )
    if session is not None and (
        session.get("localFinalized") or session.get("certificationRequestId") is not None
    ):
        return acvp_error(
            409,
            "VECTOR_SET_ALREADY_FINALIZED",
            "Vector set results cannot be changed after session finalization or certification.",
            path,
        )
    if show_expected and not _vector_set_is_sample(vector_set):
        return acvp_error(
            403,
            "EXPECTED_RESULTS_NOT_AVAILABLE",
            "showExpected is not available for non-sample vector sets.",
            path,
        )

    response = _response_with_prompt_metadata(response, vector_set)
    if legacy_direct_identity and isinstance(response, dict):
        response["vsId"] = vector_set.get("vsId")
    if isinstance(response, dict) and response.get("vsId") != vector_set.get("vsId"):
        return acvp_error(
            400,
            "VECTOR_SET_ID_MISMATCH",
            "Response vsId must match the public vector-set resource.",
            "$.vsId",
        )
    mode = normalize_acvp_json(vector_set["prompt"]).get("mode")
    try:
        module = _module_for_prompt(vector_set["prompt"], registry)
        module.validate_response(response, expected_mode=mode)
        validation_result = _validate_with_nist_genval(vector_set, response, registry)
    except AcvpSchemaError as exc:
        return acvp_error(400, exc.code, exc.message, exc.path)
    except GenValConfigurationError:
        return acvp_error(
            500,
            "NIST_GENVAL_NOT_READY",
            "NIST GenVal is not configured or built.",
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValArtifactError:
        return acvp_error(
            500,
            "NIST_GENVAL_ARTIFACT_MISSING",
            "A required NIST GenVal artifact is unavailable.",
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValExecutionError:
        return acvp_error(
            500,
            "NIST_GENVAL_EXECUTION_ERROR",
            "NIST GenVal execution failed.",
            "$",
            details=_nist_genval_error_details(),
        )
    except ValueError as exc:
        return acvp_error(400, "VALIDATION_ERROR", str(exc), "$")

    passed = _validation_passed(validation_result)
    final_status = (
        VectorSetStatus.VALIDATED.value
        if passed
        else VectorSetStatus.FAILED.value
    )
    try:
        _transition_vector_if_needed(
            vector_set,
            VectorSetStatus.RESULTS_SUBMITTED.value,
            reason="Vector set results submitted.",
        )
        vector_set["submittedAt"] = vector_set["updatedAt"]
        if session is not None:
            _transition_session_if_needed(
                session,
                TestSessionStatus.RESULTS_SUBMITTED.value,
                reason="At least one vector set result was submitted.",
                metadata={"vsId": vector_set["vsId"]},
            )
        _transition_vector_if_needed(
            vector_set,
            VectorSetStatus.VALIDATING.value,
            reason="Vector set results are being synchronously validated.",
        )
        vector_set["validatingAt"] = vector_set["updatedAt"]
        vector_set["response"] = response
        vector_set["validationResult"] = validation_result
        vector_set["report"] = None
        vector_set["showExpected"] = False
        _transition_vector_if_needed(
            vector_set,
            final_status,
            reason="Vector set results validated by NIST GenVal.",
            metadata={"passed": passed},
        )
        vector_set["validatedAt"] = vector_set["updatedAt"]
        if not passed:
            vector_set["failedAt"] = vector_set["updatedAt"]
        save_acvp_vector_set(vector_set)
        if session is not None:
            _apply_session_aggregate_status(session)
    except StateTransitionError as exc:
        return _state_transition_error_response(exc)

    save_acvp_vector_set(vector_set)
    if session is not None:
        save_acvp_session(session)

    acvp_results = build_acvp_vector_set_results(
        vector_set=vector_set,
        validation_result=validation_result,
        response=response,
        expected_results=vector_set.get("expectedResults"),
        show_expected=False,
    )
    vector_set["acvpResults"] = acvp_results
    save_acvp_vector_set(vector_set)

    from fastapi import Response

    return Response(status_code=204)


def get_vector_set_results(
    session_id: Optional[str],
    vector_set_id: Any,
    *,
    show_expected: bool = False,
) -> Any:
    if session_id is None:
        vector_set = get_vector_set_or_404(vector_set_id)
        path = f"/acvp/v1/vectorSets/{vector_set_id}/results"
    else:
        vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    if session_id is not None:
        path = f"{_nested_vector_set_path(session_id, int(vector_set['vsId']))}/results"
    session = get_acvp_session(vector_set["testSessionId"])
    if session is not None:
        legacy = _reject_legacy_local_session(session, path)
        if isinstance(legacy, JSONResponse):
            return legacy
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if show_expected and not _vector_set_is_sample(vector_set):
        return acvp_error(
            403,
            "EXPECTED_RESULTS_NOT_AVAILABLE",
            "showExpected is not available for strict non-sample vector sets.",
            path,
        )

    return build_acvp_vector_set_results(
        vector_set=vector_set,
        validation_result=vector_set.get("validationResult"),
        response=vector_set.get("response"),
        expected_results=vector_set.get("expectedResults"),
        show_expected=False,
    )


def get_test_session_results(session_id: str) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}/results"
    legacy = _reject_legacy_local_session(session, path)
    if isinstance(legacy, JSONResponse):
        return legacy
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if not session["vectorSetIds"] and session["status"] == TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return acvp_error(
            409,
            "VECTOR_SETS_NOT_GENERATED",
            "This registration session has no vector sets yet. Generate vector sets before requesting results.",
            path,
        )

    return _strict_test_session_results(session)


def _strict_test_session_results(session: Dict[str, Any]) -> Dict[str, Any]:
    results = []
    all_passed = bool(session.get("vectorSetIds"))
    for vector_set_id in session.get("vectorSetIds", []):
        vector_set = get_acvp_vector_set(vector_set_id)
        if vector_set is None:
            disposition = "unreceived"
        else:
            acvp_results = build_acvp_vector_set_results(
                vector_set=vector_set,
                validation_result=vector_set.get("validationResult"),
                response=vector_set.get("response"),
                expected_results=vector_set.get("expectedResults"),
                show_expected=False,
            )
            disposition = str(
                acvp_results.get("results", {}).get("disposition", "unreceived")
            )
        all_passed = all_passed and disposition == "passed"
        results.append(
            {
                "vectorSetUrl": _nested_vector_set_path(
                    session["testSessionId"], int(vector_set["vsId"])
                ) if vector_set is not None else None,
                "status": disposition,
                "disposition": disposition,
            }
        )

    return {
        "passed": all_passed,
        "results": results,
    }


def certify_test_session(
    session_id: str,
    certification: AcvpV1TestSessionCertificationRequest,
) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}"
    legacy = _reject_legacy_local_session(session, path)
    if isinstance(legacy, JSONResponse):
        return legacy
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable

    summary = _session_result_summary(session)
    if summary["totalVectorSets"] == 0:
        return acvp_error(
            409,
            "VECTOR_SETS_NOT_GENERATED",
            "The test session has no vector sets to certify.",
            path,
        )
    if summary["pendingVectorSets"] > 0:
        return acvp_error(
            409,
            "VECTOR_SET_RESULTS_INCOMPLETE",
            "All vector set results must be submitted before certification.",
            path,
        )
    if not summary["sessionPassed"]:
        return acvp_error(
            409,
            "TEST_SESSION_NOT_PASSED",
            "Only a test session whose NIST GenVal results all passed can be certified.",
            path,
        )

    payload = certification.model_dump(exclude_none=True)
    existing = get_acvp_request_for_session(session_id)
    if existing is not None:
        if existing["certification"] != payload:
            return acvp_error(
                409,
                "CERTIFICATION_REQUEST_CONFLICT",
                "A different certification request already exists for this test session.",
                path,
            )
        return _public_request_resource(existing)

    request = create_acvp_request(
        session_id,
        payload,
        status="initial",
        message="Awaiting processing by an external validation authority.",
    )
    session["certificationRequestId"] = request["requestId"]
    session["certificationSubmittedAt"] = request["createdAt"]
    save_acvp_session(session)
    return _public_request_resource(request)


def get_request_resource(request_id: int) -> Any:
    request = get_acvp_request(request_id)
    path = f"/acvp/v1/requests/{request_id}"
    if request is None:
        return acvp_error(
            404,
            "UNKNOWN_REQUEST",
            "Unknown ACVP request resource.",
            path,
        )

    session = get_acvp_session(request["testSessionId"])
    if session is not None:
        _expire_session_if_needed(session)
        if (
            request["status"] in {"initial", "processing"}
            and session["status"] in {
                TestSessionStatus.CANCELLED.value,
                TestSessionStatus.EXPIRED.value,
            }
        ):
            request["status"] = "rejected"
            request["message"] = (
                "Certification request rejected because the test session is "
                f"{session['status']}."
            )
            request["updatedAt"] = _timestamp()
            save_acvp_request(request)
    return _public_request_resource(request)


def _public_request_resource(request: Dict[str, Any]) -> Dict[str, Any]:
    body = {
        "url": request["url"],
        "status": request["status"],
    }
    if request.get("message") is not None:
        body["message"] = request["message"]
    if request.get("approvedUrl") is not None:
        body["approvedUrl"] = request["approvedUrl"]
    return body


def submit_test_session_for_validation(session_id: str) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}/submit"
    legacy = _reject_legacy_local_session(session, path)
    if isinstance(legacy, JSONResponse):
        return legacy
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if not session["vectorSetIds"] and session["status"] == TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return acvp_error(
            409,
            "VECTOR_SETS_NOT_GENERATED",
            "This registration session has no vector sets yet. Generate vector sets before session submit.",
            path,
        )

    summary = _session_result_summary(session)
    if summary["submittedVectorSets"] == 0:
        return acvp_error(
            409,
            "RESULTS_NOT_SUBMITTED",
            "No vector set results have been submitted for this test session.",
            path,
        )
    if summary["pendingVectorSets"] > 0:
        return acvp_error(
            409,
            "VECTOR_SET_RESULTS_INCOMPLETE",
            "All vector set results must be submitted before session-level validation.",
            path,
        )

    if not session.get("localFinalized"):
        final_status = (
            TestSessionStatus.FAILED.value
            if summary["failedVectorSets"] > 0
            else TestSessionStatus.VALIDATED.value
        )
        try:
            _transition_session_if_needed(
                session,
                TestSessionStatus.VALIDATING.value,
                reason="Session submitted for validation.",
            )
            _transition_session_if_needed(
                session,
                final_status,
                reason="Session aggregate validation finalized.",
                metadata={"sessionPassed": final_status == TestSessionStatus.VALIDATED.value},
            )
        except StateTransitionError as exc:
            return _state_transition_error_response(exc)
        session["localFinalized"] = True
        session["localFinalizedAt"] = session["updatedAt"]
        save_acvp_session(session)
        summary = _session_result_summary(session)

    return with_server_metadata(
        {
            "testSessionId": session_id,
            "status": session["status"],
            "summary": summary,
            "localExtension": True,
            "deprecated": True,
            "localFinalized": session.get("localFinalized", False),
            "localFinalizedAt": session.get("localFinalizedAt"),
            "stateHistory": _public_state_history(session.get("stateHistory", [])),
        }
    )


def delete_test_session(session_id: str) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}"
    unavailable = _reject_if_session_unavailable(session, path, allow_cancelled=True)
    if isinstance(unavailable, JSONResponse):
        return unavailable

    if session["status"] != TestSessionStatus.CANCELLED.value:
        try:
            transition_session(
                session,
                TestSessionStatus.CANCELLED.value,
                reason="Test session cancelled by DELETE request.",
            )
            for vector_set_id in list(session["vectorSetIds"]):
                vector_set = get_acvp_vector_set(vector_set_id)
                if vector_set is not None and not is_terminal_status(vector_set["status"]):
                    transition_vector_set(
                        vector_set,
                        VectorSetStatus.CANCELLED.value,
                        reason="Parent test session cancelled.",
                    )
                    vector_set["cancelledAt"] = vector_set["updatedAt"]
                    save_acvp_vector_set(vector_set)
            session["cancelledAt"] = session["updatedAt"]
            save_acvp_session(session)
        except StateTransitionError as exc:
            return _state_transition_error_response(exc)

    return with_server_metadata(
        {
            "cancelled": True,
            "testSessionId": session_id,
            "status": session["status"],
            "stateHistory": _public_state_history(session.get("stateHistory", [])),
        }
    )


def cancel_vector_set(session_id: Optional[str], vector_set_id: Any) -> Any:
    if session_id is None:
        vector_set = get_vector_set_or_404(vector_set_id)
        path = f"/acvp/v1/vectorSets/{vector_set_id}"
    else:
        vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    if session_id is not None:
        path = _nested_vector_set_path(session_id, int(vector_set["vsId"]))
    unavailable = _reject_if_vector_unavailable(vector_set, path, allow_cancelled=True)
    if isinstance(unavailable, JSONResponse):
        return unavailable

    if vector_set["status"] != VectorSetStatus.CANCELLED.value:
        try:
            transition_vector_set(
                vector_set,
                VectorSetStatus.CANCELLED.value,
                reason="Vector set cancelled by DELETE request.",
            )
            vector_set["cancelledAt"] = vector_set["updatedAt"]
            save_acvp_vector_set(vector_set)
            _cancel_session_if_all_vector_sets_cancelled(vector_set["testSessionId"])
        except StateTransitionError as exc:
            return _state_transition_error_response(exc)

    return with_server_metadata(
        {
            "cancelled": vector_set["status"] == VectorSetStatus.CANCELLED.value,
            "vectorSetId": int(vector_set["vsId"]),
            "vsId": int(vector_set["vsId"]),
            "testSessionId": vector_set["testSessionId"],
            "status": vector_set["status"],
            "stateHistory": _public_state_history(vector_set.get("stateHistory", [])),
        }
    )


def get_session_or_404(session_id: str) -> Any:
    session = get_acvp_session(session_id)
    if session is None:
        return acvp_error(
            404,
            "UNKNOWN_TEST_SESSION",
            "Unknown testSessionId.",
            f"/acvp/v1/testSessions/{session_id}",
        )
    return session


def get_vector_set_or_404(vector_set_id: str) -> Any:
    vector_set = get_acvp_vector_set(vector_set_id)
    if vector_set is None:
        return acvp_error(
            404,
            "UNKNOWN_VECTOR_SET",
            "Unknown vectorSetId.",
            f"/acvp/v1/vectorSets/{vector_set_id}",
        )
    return vector_set


def get_vector_set_for_session_or_404(session_id: str, vs_id: Any) -> Any:
    session = get_session_or_404(session_id)
    if isinstance(session, JSONResponse):
        return session
    numeric_vs_id: Optional[int] = None
    if isinstance(vs_id, int) and not isinstance(vs_id, bool):
        numeric_vs_id = vs_id
    elif isinstance(vs_id, str) and vs_id.isdigit():
        numeric_vs_id = int(vs_id)

    if numeric_vs_id is not None:
        vector_set = get_acvp_vector_set_by_vs_id(session_id, numeric_vs_id)
    else:
        vector_set = get_acvp_vector_set(str(vs_id))
        if vector_set is not None and vector_set.get("testSessionId") != session_id:
            vector_set = None
    if vector_set is None:
        return acvp_error(
            404,
            "UNKNOWN_VECTOR_SET",
            "Unknown vectorSetId for test session.",
            f"/acvp/v1/testSessions/{session_id}/vectorSets",
        )
    return vector_set


def legacy_vector_set_canonical_path(
    session_id: str,
    internal_vector_set_id: str,
    *,
    suffix: str = "",
) -> Any:
    session = get_session_or_404(session_id)
    if isinstance(session, JSONResponse):
        return session
    vector_set = get_acvp_vector_set(internal_vector_set_id)
    if vector_set is None or vector_set.get("testSessionId") != session_id:
        return acvp_error(
            404,
            "UNKNOWN_VECTOR_SET",
            "Unknown legacy vector-set resource for test session.",
            f"/acvp/v1/testSessions/{session_id}/vectorSets",
        )
    return f"{_nested_vector_set_path(session_id, int(vector_set['vsId']))}{suffix}"


def _get_session(session_id: str) -> Any:
    return get_session_or_404(session_id)


def _legacy_local_session(session: Dict[str, Any]) -> bool:
    """Classify records created before the strict-only policy without converting them."""
    if session.get("workflowPolicy") == WORKFLOW_POLICY and session.get("executionBackend") == EXECUTION_BACKEND:
        return False
    if session.get("workflowProfile") == WORKFLOW_POLICY:
        session["workflowPolicy"] = WORKFLOW_POLICY
        session["executionBackend"] = EXECUTION_BACKEND
        save_acvp_session(session)
        return False
    vector_sets = _session_vector_sets(session)
    if vector_sets and all(vector.get("provider") == NIST_GENVAL_PROVIDER_ID for vector in vector_sets):
        session["workflowPolicy"] = WORKFLOW_POLICY
        session["executionBackend"] = EXECUTION_BACKEND
        save_acvp_session(session)
        return False
    return True


def _reject_legacy_local_session(session: Dict[str, Any], path: str) -> Optional[JSONResponse]:
    if not _legacy_local_session(session):
        return None
    return acvp_error(
        409,
        "LEGACY_LOCAL_SESSION_NOT_SUPPORTED",
        "Legacy local sessions cannot be generated, submitted, or validated by the strict service.",
        path,
    )


def _session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    vector_set_summaries = [
        _vector_set_summary(vector_set)
        for vector_set_id in session["vectorSetIds"]
        for vector_set in [get_acvp_vector_set(vector_set_id)]
        if vector_set is not None
    ]
    first_summary = vector_set_summaries[0] if vector_set_summaries else {}
    result_summary = _session_result_summary(session)
    vs_ids = [int(item["vsId"]) for item in vector_set_summaries]
    vector_set_urls = [
        _nested_vector_set_path(session["testSessionId"], vs_id)
        for vs_id in vs_ids
    ]
    summary = {
        "testSessionId": session["testSessionId"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "expiresAt": session.get("expiresAt"),
        "status": session["status"],
        "label": session.get("label"),
        "vectorSetIds": vs_ids,
        "vsIds": vs_ids,
        "vectorSetUrls": vector_set_urls,
        "vectorSetCount": len(session["vectorSetIds"]),
        "downloadedVectorSetCount": result_summary["downloadedVectorSets"],
        "submittedVectorSetCount": result_summary["submittedVectorSets"],
        "validatedVectorSetCount": result_summary["validatedVectorSets"],
        "failedVectorSetCount": result_summary["failedVectorSets"],
        "pendingVectorSetCount": result_summary["pendingVectorSets"],
        "passed": result_summary["sessionPassed"],
        "publishable": result_summary["sessionPassed"],
        "algorithm": first_summary.get("algorithm"),
        "mode": first_summary.get("mode"),
        "revision": first_summary.get("revision"),
        "testGroupCount": first_summary.get("testGroupCount", 0),
        "testCaseCount": first_summary.get("testCaseCount", 0),
        "stateHistory": _public_state_history(session.get("stateHistory", [])),
        **SERVER_METADATA,
    }
    if _legacy_local_session(session):
        summary["legacy"] = True
        summary["legacyStatus"] = "unsupported"
    if "negotiatedCapabilities" in session:
        summary["negotiatedCapabilities"] = session["negotiatedCapabilities"]
        summary["negotiationWarnings"] = session.get("negotiationWarnings", [])
        summary["unsupported"] = session.get("unsupported", [])
        summary["nextAction"] = session.get("nextAction", VECTOR_GENERATION_AVAILABLE_ACTION)
    if "vectorGeneration" in session:
        summary["vectorGeneration"] = session["vectorGeneration"]
    return summary


def _vector_set_summary(vector_set: Dict[str, Any]) -> Dict[str, Any]:
    prompt_summary = summarize_vector_set(normalize_acvp_json(vector_set["prompt"]))
    vs_id = int(vector_set.get("vsId", prompt_summary["vsId"]))
    return {
        "vectorSetId": vs_id,
        "vsId": vs_id,
        "testSessionId": vector_set["testSessionId"],
        "status": vector_set["status"],
        "url": _nested_vector_set_path(
            vector_set["testSessionId"],
            vs_id,
        ),
        "generatedFromCapabilities": vector_set.get("generatedFromCapabilities", False),
        "campaignSeed": vector_set.get("campaignSeed"),
        "provider": vector_set.get("provider"),
        "providerName": vector_set.get("providerName"),
        "hasInternalProjection": vector_set.get("hasInternalProjection", False),
        "nistSourceCommit": vector_set.get("nistSourceCommit"),
        "mode": vector_set.get("mode", prompt_summary.get("mode")),
        "downloadedAt": vector_set.get("downloadedAt"),
        "submittedAt": vector_set.get("submittedAt"),
        "validatedAt": vector_set.get("validatedAt"),
        "failedAt": vector_set.get("failedAt"),
        "cancelledAt": vector_set.get("cancelledAt"),
        "expiresAt": vector_set.get("expiresAt"),
        "stateHistory": _public_state_history(vector_set.get("stateHistory", [])),
        **prompt_summary,
        **SERVER_METADATA,
    }


def _nested_vector_set_path(session_id: str, vs_id: int) -> str:
    return f"/acvp/v1/testSessions/{session_id}/vectorSets/{vs_id}"


def _public_state_history(history: Any) -> List[Dict[str, Any]]:
    public_history: List[Dict[str, Any]] = []
    for raw_event in history if isinstance(history, list) else []:
        if not isinstance(raw_event, dict):
            continue
        event = dict(raw_event)
        metadata = event.get("metadata")
        if isinstance(metadata, dict):
            public_metadata = dict(metadata)
            public_metadata.pop("vectorSetId", None)
            public_metadata.pop("internalVectorSetId", None)
            event["metadata"] = public_metadata
        public_history.append(event)
    return public_history


def _response_with_prompt_metadata(response: Any, vector_set: Dict[str, Any]) -> Any:
    if not isinstance(response, dict):
        return response
    normalized = dict(response)
    normalized.pop("showExpected", None)
    try:
        prompt = normalize_acvp_json(vector_set["prompt"])
    except Exception:
        prompt = {}
    for key in ("vsId", "algorithm", "mode", "revision"):
        if normalized.get(key) is None and prompt.get(key) is not None:
            normalized[key] = prompt[key]
    return normalized


def _validate_with_nist_genval(
    vector_set: Dict[str, Any],
    response: Any,
    registry: AlgorithmModuleRegistry,
) -> Dict[str, Any]:
    settings = get_genval_settings()
    artifact_paths = dict(vector_set.get("artifactPaths") or {})
    work_dir = Path(
        artifact_paths.get("root")
        or vector_set_artifact_dir(
            settings.artifact_root,
            vector_set["testSessionId"],
            vector_set["vectorSetId"],
        )
    )
    internal_projection_value = artifact_paths.get("internalProjection")
    if not internal_projection_value:
        raise GenValArtifactError(
            f"NIST internalProjection path is missing for vector set {vector_set['vectorSetId']}"
        )

    response_path = work_dir / "response.json"
    _write_json_file(response_path, response)
    validation_path = NistCliGenValProvider(settings).validate(
        Path(internal_projection_value),
        response_path,
        work_dir,
    )
    validation_payload = _read_json_file(validation_path)

    artifact_paths.update(
        {
            "root": str(work_dir),
            "response": str(response_path),
            "validation": str(validation_path),
            "validationStdout": str(work_dir / "validation.stdout.txt"),
            "validationStderr": str(work_dir / "validation.stderr.txt"),
        }
    )
    vector_set["artifactPaths"] = artifact_paths

    validation_result = _normalize_validation_for_prompt(
        validation_payload,
        vector_set["prompt"],
        registry,
    )
    validation_result["metadata"]["providerName"] = NIST_GENVAL_PROVIDER_NAME
    validation_result["metadata"]["executionBackend"] = EXECUTION_BACKEND
    validation_result["metadata"]["validationArtifact"] = str(validation_path)
    return validation_result


def _normalize_validation_for_prompt(
    validation: Dict[str, Any],
    prompt: Dict[str, Any],
    registry: AlgorithmModuleRegistry,
) -> Dict[str, Any]:
    module = _module_for_prompt(prompt, registry)
    return normalize_module_validation(module, validation, prompt=prompt)


def _get_session_label(session_id: str) -> Optional[str]:
    session = get_acvp_session(session_id)
    if session is None:
        return None
    label = session.get("label")
    return str(label) if label is not None else None


def _validation_passed(validation_result: Dict[str, Any]) -> bool:
    summary = validation_result["summary"]
    return (
        summary["failed"] == 0
        and summary["missing"] == 0
        and summary["malformed"] == 0
        and summary.get("extra", 0) == 0
    )


def _record_created(entity: Dict[str, Any], to_status: str, reason: str) -> None:
    add_state_event(
        entity,
        event="created",
        from_status=None,
        to_status=to_status,
        reason=reason,
    )


def _transition_session_if_needed(
    session: Dict[str, Any],
    to_status: str,
    *,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if session["status"] == to_status:
        return
    transition_session(session, to_status, reason=reason, metadata=metadata)


def _transition_vector_if_needed(
    vector_set: Dict[str, Any],
    to_status: str,
    *,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if vector_set["status"] == to_status:
        return
    transition_vector_set(vector_set, to_status, reason=reason, metadata=metadata)


def _mark_session_downloaded_if_complete(session_id: str) -> None:
    session = get_acvp_session(session_id)
    if session is None or session["status"] != TestSessionStatus.VECTOR_READY.value:
        return
    vector_sets = _session_vector_sets(session)
    if not vector_sets:
        return
    if all(vector_set.get("downloadedAt") for vector_set in vector_sets):
        transition_session(
            session,
            TestSessionStatus.VECTOR_DOWNLOADED.value,
            reason="All vector sets have been downloaded.",
        )
        save_acvp_session(session)


def _apply_session_aggregate_status(session: Dict[str, Any]) -> None:
    summary = _session_result_summary(session)
    if summary["submittedVectorSets"] == 0:
        return
    if summary["pendingVectorSets"] > 0:
        _transition_session_if_needed(
            session,
            TestSessionStatus.RESULTS_SUBMITTED.value,
            reason="Some vector set results are submitted; other vector sets are pending.",
        )
        return

    final_status = (
        TestSessionStatus.FAILED.value
        if summary["failedVectorSets"] > 0
        else TestSessionStatus.VALIDATED.value
    )
    _transition_session_if_needed(
        session,
        TestSessionStatus.VALIDATING.value,
        reason="All vector set results are available for session aggregate validation.",
    )
    _transition_session_if_needed(
        session,
        final_status,
        reason="Session aggregate validation completed.",
        metadata={"sessionPassed": final_status == TestSessionStatus.VALIDATED.value},
    )


def _session_result_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    vector_sets = _session_vector_sets(session)
    total = len(session.get("vectorSetIds", []))
    downloaded = sum(1 for vector_set in vector_sets if vector_set.get("downloadedAt"))
    submitted = sum(
        1
        for vector_set in vector_sets
        if vector_set.get("submittedAt") or vector_set.get("validationResult") is not None
    )
    validated = sum(
        1
        for vector_set in vector_sets
        if vector_set.get("status") == VectorSetStatus.VALIDATED.value
    )
    failed = sum(
        1
        for vector_set in vector_sets
        if vector_set.get("status") == VectorSetStatus.FAILED.value
    )
    pending = max(total - submitted, 0)
    session_passed = total > 0 and pending == 0 and failed == 0 and validated == total
    return {
        "totalVectorSets": total,
        "downloadedVectorSets": downloaded,
        "submittedVectorSets": submitted,
        "validatedVectorSets": validated,
        "passedVectorSets": validated,
        "failedVectorSets": failed,
        "pendingVectorSets": pending,
        "sessionPassed": session_passed,
    }


def _session_vector_sets(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    vector_sets_by_id = {
        vector_set["vectorSetId"]: vector_set
        for vector_set in list_acvp_vector_sets_for_session(session["testSessionId"])
    }
    return [
        vector_sets_by_id[vector_set_id]
        for vector_set_id in session.get("vectorSetIds", [])
        if vector_set_id in vector_sets_by_id
    ]


def _reject_if_session_unavailable(
    session: Dict[str, Any],
    path: str,
    *,
    allow_cancelled: bool = False,
) -> Optional[JSONResponse]:
    _expire_session_if_needed(session)
    if session["status"] == TestSessionStatus.EXPIRED.value:
        return acvp_error(
            409,
            "TEST_SESSION_EXPIRED",
            "Test session has expired in the local skeleton state machine.",
            path,
        )
    if session["status"] == TestSessionStatus.CANCELLED.value and not allow_cancelled:
        return acvp_error(
            409,
            "TEST_SESSION_CANCELLED",
            "Test session has been cancelled.",
            path,
        )
    return None


def _reject_if_vector_unavailable(
    vector_set: Dict[str, Any],
    path: str,
    *,
    allow_cancelled: bool = False,
) -> Optional[JSONResponse]:
    session = get_acvp_session(vector_set["testSessionId"])
    if session is not None:
        session_error = _reject_if_session_unavailable(
            session,
            path,
            allow_cancelled=allow_cancelled,
        )
        if isinstance(session_error, JSONResponse):
            return session_error

    _expire_vector_set_if_needed(vector_set)
    if vector_set["status"] == VectorSetStatus.EXPIRED.value:
        return acvp_error(
            409,
            "VECTOR_SET_EXPIRED",
            "Vector set has expired in the local skeleton state machine.",
            path,
        )
    if vector_set["status"] == VectorSetStatus.CANCELLED.value and not allow_cancelled:
        return acvp_error(
            409,
            "VECTOR_SET_CANCELLED",
            "Vector set has been cancelled.",
            path,
        )
    return None


def _expire_session_if_needed(session: Dict[str, Any]) -> bool:
    if is_terminal_status(session["status"]) or not session_is_expired(session):
        return False
    transition_session(
        session,
        TestSessionStatus.EXPIRED.value,
        reason="Test session expiresAt was reached.",
    )
    session["expiredAt"] = session["updatedAt"]
    for vector_set in _session_vector_sets(session):
        if not is_terminal_status(vector_set["status"]):
            transition_vector_set(
                vector_set,
                VectorSetStatus.EXPIRED.value,
                reason="Parent test session expired.",
            )
            vector_set["expiredAt"] = vector_set["updatedAt"]
            save_acvp_vector_set(vector_set)
    save_acvp_session(session)
    return True


def _expire_vector_set_if_needed(vector_set: Dict[str, Any]) -> bool:
    if is_terminal_status(vector_set["status"]) or not vector_set_is_expired(vector_set):
        return False
    transition_vector_set(
        vector_set,
        VectorSetStatus.EXPIRED.value,
        reason="Vector set expiresAt was reached.",
    )
    vector_set["expiredAt"] = vector_set["updatedAt"]
    save_acvp_vector_set(vector_set)
    session = get_acvp_session(vector_set["testSessionId"])
    if session is not None and not is_terminal_status(session["status"]):
        vector_sets = _session_vector_sets(session)
        if vector_sets and all(
            item["status"] == VectorSetStatus.EXPIRED.value for item in vector_sets
        ):
            transition_session(
                session,
                TestSessionStatus.EXPIRED.value,
                reason="All vector sets in the session expired.",
            )
            session["expiredAt"] = session["updatedAt"]
            save_acvp_session(session)
    return True


def _cancel_session_if_all_vector_sets_cancelled(session_id: str) -> None:
    session = get_acvp_session(session_id)
    if session is None or is_terminal_status(session["status"]):
        return
    vector_sets = _session_vector_sets(session)
    if vector_sets and all(
        vector_set["status"] == VectorSetStatus.CANCELLED.value
        for vector_set in vector_sets
    ):
        transition_session(
            session,
            TestSessionStatus.CANCELLED.value,
            reason="All vector sets in the session were cancelled.",
        )
        session["cancelledAt"] = session["updatedAt"]
        save_acvp_session(session)


def _state_transition_error_response(exc: StateTransitionError) -> JSONResponse:
    return acvp_error(409, exc.code, exc.message, exc.path)


def _validate_status_filter(
    status: Optional[str],
    *,
    allowed: set,
    entity: str,
) -> Optional[JSONResponse]:
    if status is None:
        return None
    if status not in allowed:
        return acvp_error(
            400,
            "INVALID_QUERY_PARAMETER",
            f"Unsupported {entity} status filter.",
            "$.status",
            details={
                "parameter": "status",
                "value": status,
                "allowed": sorted(allowed),
            },
        )
    return None


def _expires_at_from_seconds(expires_in_seconds: Optional[int]) -> Optional[str]:
    if expires_in_seconds is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat()


def _timestamp() -> str:
    return now_timestamp()
