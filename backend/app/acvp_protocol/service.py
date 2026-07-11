from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi.responses import JSONResponse

from ..acvp_core.algorithm_provider import (
    AcvpAlgorithmProvider,
    AcvpProviderExecutionError,
    AcvpProviderInputError,
)
from ..acvp_core.registry import ProviderNotFoundError, get_provider, list_algorithms
from ..acvp_mldsa.errors import AcvpSchemaError
from ..acvp_mldsa.nist_registration_mapper import map_mldsa_registration_container_to_nist
from ..acvp_mldsa.nist_validation_mapper import normalize_nist_validation
from ..acvp_mldsa.provider import ensure_mldsa_provider_registered
from ..acvp_parser import AcvpParseError, normalize_acvp_json, summarize_vector_set
from ..genval import (
    GenValArtifactError,
    GenValConfigurationError,
    GenValExecutionError,
    NistCliGenValProvider,
    get_genval_settings,
)
from ..genval.artifacts import vector_set_artifact_dir
from ..models import AcvpV1TestSessionCreateRequest, AcvpV1VectorSetGenerateRequest
from ..report import build_report
from ..storage.sqlite_store import (
    ACVP_SKELETON_SESSION_STORE,
    ACVP_SKELETON_VECTOR_SET_STORE,
    delete_acvp_vector_sets_for_session,
    get_acvp_session,
    get_acvp_vector_set,
    list_acvp_sessions,
    list_acvp_vector_sets_for_session,
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
from .workflow_profile import (
    LOCAL_WORKFLOW_PROFILE,
    STRICT_WORKFLOW_PROFILE,
    is_strict_workflow,
)

ensure_mldsa_provider_registered()

SKELETON_PROFILE = "local-fips204-skeleton"
NIST_GENVAL_PROVIDER_ID = "nist-genval"
NIST_GENVAL_PROVIDER_NAME = "NIST ACVP-Server GenValAppRunner"
SKELETON_METADATA: Dict[str, Any] = {
    "productionReady": False,
    "profile": SKELETON_PROFILE,
    "demoOnly": True,
    "notProductionAcvp": True,
}

NIST_REFERENCES = [
    "https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html",
    "https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html",
    "https://csrc.nist.gov/pubs/fips/204/final",
]

_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
VECTOR_GENERATION_AVAILABLE_ACTION = (
    "Server-side vector generation from negotiated capabilities is available in "
    "Phase 3-5; enable autoGenerateVectorSets or call /vectorSets/generate."
)


def with_skeleton_metadata(body: Dict[str, Any]) -> Dict[str, Any]:
    return {**body, **SKELETON_METADATA}


def acvp_skeleton_error(
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
    return with_skeleton_metadata(
        {
            "acvVersion": "1.0",
            "apiVersion": "v1",
            "serverName": "NCCU ACVP Server",
            "implementationPhase": "5-3-provider-interface",
            "nistReferences": NIST_REFERENCES,
        }
    )


def algorithms() -> Dict[str, Any]:
    return with_skeleton_metadata(
        {
            "algorithms": [
                {
                    "algorithm": "ML-DSA",
                    "revision": "FIPS204",
                    "modes": ["keyGen", "sigGen", "sigVer"],
                    "parameterSets": ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"],
                    "signatureInterfaces": ["internal", "external"],
                    "internal": {
                        "externalMu": [False, True],
                        "deterministic": [False, True],
                    },
                    "external": {
                        "preHash": ["pure", "preHash"],
                        "context": True,
                        "hashAlgs": [
                            "SHA2-224",
                            "SHA2-256",
                            "SHA2-384",
                            "SHA2-512",
                            "SHA2-512/224",
                            "SHA2-512/256",
                            "SHA3-224",
                            "SHA3-256",
                            "SHA3-384",
                            "SHA3-512",
                            "SHAKE-128",
                            "SHAKE-256",
                        ],
                    },
                    "localOracleLimitations": [
                        "Phase 5-3 routes /acvp/v1 registration, negotiation, vector generation, expectedResults, and response validation through the algorithm provider registry. Only ML-DSA/FIPS204 is registered.",
                        "Phase 5-2 supports SHAKE-128 and SHAKE-256 preHash generation with fixed digest lengths aligned to the native oracle mapping.",
                        "Phase 4-1 supports SQLite-backed local-fips204-skeleton persistence; production vector generation is not implemented.",
                        "Phase 4-3 Commit 1 adds ACVP array envelopes and canonical nested vectorSet routes while remaining a local skeleton.",
                        "Phase 4-3 Commit 2 adds a local ACVP results disposition adapter and showExpected support.",
                        "Phase 4-3 Commit 3 adds local paging/query hardening and normalized ACVP error envelopes.",
                        "Production auth/JWT/mTLS is not implemented.",
                        "Production database deployment is not implemented.",
                    ],
                    "nistReferences": NIST_REFERENCES,
                }
            ]
        }
    )


def _validate_registration_container_with_providers(payload: Any) -> Dict[str, Any]:
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
        provider = _provider_for_identity(algorithm, mode, revision, item_path)
        try:
            normalized = provider.validate_registration(registration)
        except AcvpSchemaError as exc:
            raise _with_prefixed_path(exc, item_path) from exc

        normalized_algorithm = str(normalized.get("algorithm"))
        normalized_mode = str(normalized.get("mode"))
        normalized_revision = str(normalized.get("revision"))
        if not provider.supports(normalized_algorithm, normalized_mode, normalized_revision):
            raise _provider_not_found_schema_error(
                ProviderNotFoundError(
                    normalized_algorithm,
                    normalized_mode,
                    normalized_revision,
                ),
                item_path,
            )

        key = (normalized_algorithm, normalized_mode, normalized_revision)
        if key in seen:
            raise AcvpSchemaError(
                "duplicate_registration",
                "Duplicate algorithm/mode/revision registration.",
                _child_path(item_path, "mode"),
            )
        seen.add(key)
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


def _negotiate_capabilities_with_providers(container: Dict[str, Any]) -> Dict[str, Any]:
    negotiated: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    identities: List[tuple[str, str]] = []

    for index, registration in enumerate(container["algorithms"]):
        item_path = _child_path("$.algorithms", index)
        algorithm = str(registration["algorithm"])
        mode = str(registration["mode"])
        revision = str(registration["revision"])
        provider = _provider_for_identity(algorithm, mode, revision, item_path)
        if (algorithm, revision) not in identities:
            identities.append((algorithm, revision))
        try:
            result = provider.negotiate_capabilities(registration)
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


def _generate_vector_sets_with_providers(
    negotiated_capabilities: Dict[str, Any],
    *,
    campaign_seed: str,
    tests_per_group: int,
    generation_profile: str,
) -> List[Dict[str, Any]]:
    buckets: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    order: List[tuple[str, str, str]] = []

    for index, entry in enumerate(negotiated_capabilities.get("negotiated", [])):
        entry_path = _child_path("$.negotiatedCapabilities.negotiated", index)
        entry_obj = _require_json_object(entry, entry_path)
        algorithm = entry_obj.get("algorithm", negotiated_capabilities.get("algorithm"))
        revision = entry_obj.get("revision", negotiated_capabilities.get("revision"))
        mode = entry_obj.get("mode")
        algorithm_text = _require_json_string(algorithm, _child_path(entry_path, "algorithm"))
        mode_text = _require_json_string(mode, _child_path(entry_path, "mode"))
        revision_text = _require_json_string(revision, _child_path(entry_path, "revision"))
        provider = _provider_for_identity(
            algorithm_text,
            mode_text,
            revision_text,
            entry_path,
        )
        key = (algorithm_text, revision_text, provider.__class__.__name__)
        if key not in buckets:
            buckets[key] = {
                "provider": provider,
                "algorithm": algorithm_text,
                "revision": revision_text,
                "entries": [],
            }
            order.append(key)
        buckets[key]["entries"].append(entry_obj)

    prompts: List[Dict[str, Any]] = []
    for key in order:
        bucket = buckets[key]
        provider = bucket["provider"]
        provider_capabilities = dict(negotiated_capabilities)
        provider_capabilities["algorithm"] = bucket["algorithm"]
        provider_capabilities["revision"] = bucket["revision"]
        provider_capabilities["negotiated"] = bucket["entries"]
        prompts.extend(
            provider.generate_vector_sets(
                provider_capabilities,
                campaign_seed=campaign_seed,
                tests_per_group=tests_per_group,
                generation_profile=generation_profile,
            )
        )
    return prompts


def _provider_for_prompt(prompt: Any) -> AcvpAlgorithmProvider:
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
    return _provider_for_identity(algorithm, mode, revision, "$")


def _provider_for_registration_container(
    registration_container: Dict[str, Any],
) -> AcvpAlgorithmProvider:
    algorithms = registration_container.get("algorithms")
    if not isinstance(algorithms, list) or not algorithms:
        raise AcvpSchemaError(
            "missing_required_field",
            "Registration container must include at least one algorithm.",
            "$.algorithms",
        )
    first_registration = _require_json_object(algorithms[0], "$.algorithms[0]")
    algorithm = _require_json_string(
        _require_json_field(first_registration, "algorithm", "$.algorithms[0]"),
        "$.algorithms[0].algorithm",
    )
    mode = _require_json_string(
        _require_json_field(first_registration, "mode", "$.algorithms[0]"),
        "$.algorithms[0].mode",
    )
    revision = _require_json_string(
        _require_json_field(first_registration, "revision", "$.algorithms[0]"),
        "$.algorithms[0].revision",
    )
    return _provider_for_identity(algorithm, mode, revision, "$.algorithms[0]")


def _provider_for_identity(
    algorithm: str,
    mode: str,
    revision: str,
    path: str,
) -> AcvpAlgorithmProvider:
    try:
        return get_provider(algorithm, mode, revision)
    except ProviderNotFoundError as exc:
        raise _provider_not_found_schema_error(exc, path) from exc


def _provider_not_found_schema_error(
    exc: ProviderNotFoundError,
    path: str,
) -> AcvpSchemaError:
    summaries = list_algorithms()
    algorithm_summary = next(
        (
            summary
            for summary in summaries
            if summary.get("algorithm") == exc.algorithm
        ),
        None,
    )
    if algorithm_summary is None:
        return AcvpSchemaError(
            "unsupported_algorithm",
            f"Unsupported algorithm provider: {exc.algorithm}",
            _child_path(path, "algorithm"),
        )

    revisions = set(algorithm_summary.get("revisions", []))
    if exc.revision not in revisions:
        return AcvpSchemaError(
            "unsupported_revision",
            f"Unsupported revision for {exc.algorithm}: {exc.revision}",
            _child_path(path, "revision"),
        )
    return AcvpSchemaError(
        "invalid_mode",
        f"Unsupported mode for {exc.algorithm}/{exc.revision}: {exc.mode}",
        _child_path(path, "mode"),
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
    return with_skeleton_metadata(
        body
    )


def create_test_session(
    payload: AcvpV1TestSessionCreateRequest,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    if payload.prompt is not None and payload.algorithms is not None:
        return acvp_skeleton_error(
            400,
            "INVALID_REQUEST",
            "prompt and algorithms cannot both be present in one test session request.",
            "$",
        )
    if payload.algorithms is not None:
        return _create_registration_session(payload, workflow_profile=workflow_profile)
    if payload.prompt is None:
        return acvp_skeleton_error(
            400,
            "INVALID_REQUEST",
            "Request must include either prompt or algorithms.",
            "$",
        )

    is_sample = _resolve_is_sample(payload.isSample, workflow_profile)
    prompt = _payload_with_is_sample(payload.prompt, is_sample)
    try:
        provider = _provider_for_prompt(prompt)
        prompt_vs = provider.validate_prompt(prompt)
        expected_results = None
        if payload.autoGenerateExpectedResults:
            expected_results = provider.generate_expected_results(prompt)
            provider.validate_response(expected_results, expected_mode=prompt_vs["mode"])
    except AcvpSchemaError as exc:
        return acvp_skeleton_error(400, exc.code, exc.message, exc.path)
    except AcvpProviderInputError as exc:
        return acvp_skeleton_error(400, "ORACLE_INPUT_ERROR", str(exc), "$")
    except AcvpProviderExecutionError as exc:
        return acvp_skeleton_error(500, "ORACLE_EXECUTION_ERROR", str(exc), "$")

    now = _timestamp()
    session_id = str(uuid4())
    vector_set_id = str(uuid4())
    vector_set_url = _nested_vector_set_path(session_id, vector_set_id)
    expires_at = _expires_at_from_seconds(payload.expiresInSeconds)

    session = {
        "testSessionId": session_id,
        "createdAt": now,
        "updatedAt": now,
        "status": TestSessionStatus.CREATED.value,
        "label": payload.label,
        "expiresAt": expires_at,
        "vectorSetIds": [vector_set_id],
        "vectorSetUrls": [vector_set_url],
        "workflowProfile": workflow_profile,
        "isSample": is_sample,
        **SKELETON_METADATA,
    }
    vector_set = {
        "vectorSetId": vector_set_id,
        "testSessionId": session_id,
        "createdAt": now,
        "updatedAt": now,
        "status": VectorSetStatus.CREATED.value,
        "expiresAt": expires_at,
        "prompt": prompt,
        "expectedResults": expected_results,
        "response": None,
        "validationResult": None,
        "report": None,
        "mode": prompt_vs["mode"],
        "vsId": prompt_vs["vsId"],
        "isSample": is_sample,
        **SKELETON_METADATA,
    }
    _record_created(session, TestSessionStatus.CREATED.value, "Prompt-based test session created.")
    _record_created(vector_set, VectorSetStatus.CREATED.value, "Prompt-based vector set created.")
    if expected_results is not None:
        transition_vector_set(
            vector_set,
            VectorSetStatus.READY.value,
            reason="Expected results generated for prompt-based vector set.",
        )
        transition_session(
            session,
            TestSessionStatus.VECTOR_READY.value,
            reason="Prompt-based vector set is ready for download.",
        )
    save_acvp_session(session)
    save_acvp_vector_set(vector_set)

    return with_skeleton_metadata(
        {
            "testSessionId": session_id,
            "status": session["status"],
            "label": payload.label,
            "vectorSetUrls": [vector_set_url],
            "vectorSetIds": [vector_set_id],
            "isSample": is_sample,
            "createdAt": now,
            "updatedAt": session["updatedAt"],
            "expiresAt": expires_at,
            "stateHistory": list(session["stateHistory"]),
        }
    )


def _create_registration_session(
    payload: AcvpV1TestSessionCreateRequest,
    *,
    workflow_profile: str,
) -> Any:
    try:
        container_payload: Dict[str, Any] = {"algorithms": payload.algorithms}
        if payload.label is not None:
            container_payload["label"] = payload.label
        if payload.metadata is not None:
            container_payload["metadata"] = payload.metadata
        registration_container = _validate_registration_container_with_providers(container_payload)
        negotiated_capabilities = _negotiate_capabilities_with_providers(registration_container)
        generation_provider = _provider_for_registration_container(registration_container)
        generation_profile = _resolve_generation_profile(
            payload.generationProfile,
            generation_provider,
        )
        generation_profile = _strict_generation_profile_if_needed(
            generation_profile,
            generation_provider,
            workflow_profile=workflow_profile,
            explicit_profile=payload.generationProfile is not None,
        )
        campaign_seed = _resolve_campaign_seed(
            payload.campaignSeed,
            registration_container,
            generation_provider,
        )
        tests_per_group = _resolve_tests_per_group(
            payload.testsPerGroup,
            generation_profile,
            generation_provider,
        )
    except AcvpSchemaError as exc:
        return acvp_skeleton_error(400, exc.code, exc.message, exc.path)

    now = _timestamp()
    session_id = str(uuid4())
    expires_at = _expires_at_from_seconds(payload.expiresInSeconds)
    is_sample = _resolve_is_sample(payload.isSample, workflow_profile)
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
        "generationProfile": generation_profile,
        "workflowProfile": workflow_profile,
        "isSample": is_sample,
        "vectorSetIds": [],
        "vectorSetUrls": [],
        "nextAction": VECTOR_GENERATION_AVAILABLE_ACTION,
        **SKELETON_METADATA,
    }
    _record_created(session, TestSessionStatus.CREATED.value, "Registration test session created.")
    transition_session(
        session,
        TestSessionStatus.CAPABILITIES_ACCEPTED.value,
        reason="Capabilities accepted by provider-based local skeleton negotiation.",
    )
    save_acvp_session(session)

    if payload.autoGenerateVectorSets:
        generated = _generate_and_store_vector_sets(
            session,
            campaign_seed=campaign_seed,
            tests_per_group=tests_per_group,
            generation_profile=generation_profile,
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


def generate_vector_sets_for_session(
    session_id: str,
    payload: AcvpV1VectorSetGenerateRequest,
) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}/vectorSets/generate"
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if "negotiatedCapabilities" not in session:
        return acvp_skeleton_error(
            409,
            "NEGOTIATED_CAPABILITIES_NOT_AVAILABLE",
            "This test session was not created from a registration container.",
            path,
        )
    if session["vectorSetIds"]:
        return acvp_skeleton_error(
            409,
            "VECTOR_SETS_ALREADY_GENERATED",
            "Vector sets have already been generated for this test session.",
            path,
        )
    if session["status"] != TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return acvp_skeleton_error(
            409,
            "INVALID_SESSION_STATE",
            "Vector sets can only be generated for a capabilitiesAccepted session.",
            path,
        )

    try:
        generation_provider = _provider_for_registration_container(session["registration"])
        campaign_seed = _resolve_campaign_seed(
            payload.campaignSeed if payload.campaignSeed is not None else session.get("campaignSeed"),
            session["registration"],
            generation_provider,
        )
        generation_profile = _resolve_generation_profile(
            payload.generationProfile
            if payload.generationProfile is not None
            else session.get("generationProfile"),
            generation_provider,
        )
        generation_profile = _strict_generation_profile_if_needed(
            generation_profile,
            generation_provider,
            workflow_profile=str(session.get("workflowProfile", LOCAL_WORKFLOW_PROFILE)),
            explicit_profile=payload.generationProfile is not None,
        )
        tests_per_group = _resolve_tests_per_group(
            payload.testsPerGroup if payload.testsPerGroup is not None else session.get("testsPerGroup"),
            generation_profile,
            generation_provider,
        )
    except AcvpSchemaError as exc:
        return acvp_skeleton_error(400, exc.code, exc.message, exc.path)

    generated = _generate_and_store_vector_sets(
        session,
        campaign_seed=campaign_seed,
        tests_per_group=tests_per_group,
        generation_profile=generation_profile,
        expires_at=_expires_at_from_seconds(payload.expiresInSeconds) or session.get("expiresAt"),
        is_sample=_vector_set_session_is_sample(session),
        reason="Explicit vector generation endpoint called.",
    )
    if isinstance(generated, JSONResponse):
        return generated
    return _registration_session_response(session)


def _registration_session_response(session: Dict[str, Any]) -> Dict[str, Any]:
    response = {
        "testSessionId": session["testSessionId"],
        "status": session["status"],
        "label": session.get("label"),
        "negotiatedCapabilities": session["negotiatedCapabilities"],
        "negotiationWarnings": session["negotiationWarnings"],
        "unsupported": session["unsupported"],
        "vectorSetIds": list(session["vectorSetIds"]),
        "vectorSetUrls": list(session["vectorSetUrls"]),
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "expiresAt": session.get("expiresAt"),
        "campaignSeed": session.get("campaignSeed"),
        "testsPerGroup": session.get("testsPerGroup"),
        "generationProfile": session.get("generationProfile"),
        "isSample": session.get("isSample"),
        "stateHistory": list(session.get("stateHistory", [])),
    }
    if "vectorGeneration" in session:
        response["vectorGeneration"] = session["vectorGeneration"]
    else:
        response["nextAction"] = VECTOR_GENERATION_AVAILABLE_ACTION
    return with_skeleton_metadata(response)


def _generate_and_store_vector_sets(
    session: Dict[str, Any],
    *,
    campaign_seed: str,
    tests_per_group: int,
    generation_profile: str,
    expires_at: Optional[str],
    is_sample: bool,
    reason: str,
) -> Optional[JSONResponse]:
    use_nist_genval = _should_use_nist_genval(session, generation_profile)
    try:
        if use_nist_genval:
            prepared = _prepare_nist_generated_vector_sets(
                session,
                campaign_seed=campaign_seed,
                generation_profile=generation_profile,
                is_sample=is_sample,
            )
        else:
            prompts = _generate_vector_sets_with_providers(
                session["negotiatedCapabilities"],
                campaign_seed=campaign_seed,
                tests_per_group=tests_per_group,
                generation_profile=generation_profile,
            )
            prepared = _prepare_generated_vector_sets(
                session["testSessionId"],
                prompts,
                campaign_seed,
                generation_profile,
                is_sample,
            )
    except AcvpSchemaError as exc:
        return acvp_skeleton_error(500, exc.code, exc.message, exc.path)
    except GenValConfigurationError as exc:
        return acvp_skeleton_error(
            500,
            "NIST_GENVAL_NOT_READY",
            str(exc),
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValArtifactError as exc:
        return acvp_skeleton_error(
            500,
            "NIST_GENVAL_ARTIFACT_MISSING",
            str(exc),
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValExecutionError as exc:
        return acvp_skeleton_error(
            500,
            "NIST_GENVAL_EXECUTION_ERROR",
            str(exc),
            "$",
            details=_nist_genval_error_details(),
        )
    except AcvpProviderInputError as exc:
        return acvp_skeleton_error(400, "ORACLE_INPUT_ERROR", str(exc), "$")
    except AcvpProviderExecutionError as exc:
        return acvp_skeleton_error(500, "ORACLE_EXECUTION_ERROR", str(exc), "$")
    except ValueError as exc:
        return acvp_skeleton_error(500, "VECTOR_GENERATION_ERROR", str(exc), "$")

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
            reason="Expected results generated for negotiated vector set.",
            metadata={"generationProfile": generation_profile},
        )
        save_acvp_vector_set(vector_set)
        vector_set_ids.append(vector_set["vectorSetId"])
        vector_set_urls.append(
            _nested_vector_set_path(session["testSessionId"], vector_set["vectorSetId"])
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
            "generationProfile": generation_profile,
            "generatedVectorSetCount": len(vector_set_ids),
            "provider": NIST_GENVAL_PROVIDER_ID if use_nist_genval else "local-python",
        },
    )
    session["campaignSeed"] = campaign_seed
    session["testsPerGroup"] = tests_per_group
    session["generationProfile"] = generation_profile
    session["vectorSetIds"] = vector_set_ids
    session["vectorSetUrls"] = vector_set_urls
    session["nextAction"] = "Download vector sets and submit results."
    session["vectorGeneration"] = {
        "campaignSeed": campaign_seed,
        "testsPerGroup": tests_per_group,
        "effectiveMinimums": _generation_profile_minimums(
            generation_profile,
            _provider_for_registration_container(session["registration"]),
        ),
        "generatedVectorSetCount": len(vector_set_ids),
        "modes": [
            normalize_acvp_json(vector_set["prompt"])["mode"]
            for vector_set in prepared
        ],
        "generationProfile": generation_profile,
        "provider": NIST_GENVAL_PROVIDER_ID if use_nist_genval else "local-python",
        "providerName": NIST_GENVAL_PROVIDER_NAME if use_nist_genval else "Local Python ML-DSA provider",
        "localSkeletonBehavior": not use_nist_genval,
        "expectedResultsDebugOnly": use_nist_genval,
        "hasInternalProjection": use_nist_genval,
    }
    save_acvp_session(session)
    return None


def _prepare_generated_vector_sets(
    session_id: str,
    prompts: List[Dict[str, Any]],
    campaign_seed: str,
    generation_profile: str,
    is_sample: bool,
) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for raw_prompt in prompts:
        prompt = _payload_with_is_sample(raw_prompt, is_sample)
        provider = _provider_for_prompt(prompt)
        prompt_vs = provider.validate_prompt(prompt)
        expected_results = provider.generate_expected_results(prompt)
        provider.validate_response(expected_results, expected_mode=prompt_vs["mode"])
        vector_set_id = str(uuid4())
        prepared.append(
            {
                "vectorSetId": vector_set_id,
                "testSessionId": session_id,
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
                "generationProfile": generation_profile,
                "isSample": is_sample,
                **SKELETON_METADATA,
            }
        )
    return prepared


def _prepare_nist_generated_vector_sets(
    session: Dict[str, Any],
    *,
    campaign_seed: str,
    generation_profile: str,
    is_sample: bool,
) -> List[Dict[str, Any]]:
    settings = get_genval_settings()
    genval_provider = NistCliGenValProvider(settings)
    source_commit = _nist_source_commit(settings.project_root)
    nist_registrations = map_mldsa_registration_container_to_nist(
        session["registration"],
        is_sample=is_sample,
        starting_vs_id=1,
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
        provider = _provider_for_prompt(prompt)
        prompt_vs = provider.validate_prompt(prompt)
        provider.validate_response(expected_results, expected_mode=prompt_vs["mode"])

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
                "generationProfile": generation_profile,
                "isSample": is_sample,
                "provider": NIST_GENVAL_PROVIDER_ID,
                "providerName": NIST_GENVAL_PROVIDER_NAME,
                "expectedResultsDebugOnly": True,
                "hasInternalProjection": True,
                "nistSourceCommit": source_commit,
                "artifactPaths": _genval_artifact_paths(work_dir, artifacts),
                **SKELETON_METADATA,
            }
        )
    return prepared


def _should_use_nist_genval(
    session: Dict[str, Any],
    generation_profile: str,
) -> bool:
    workflow_profile = str(session.get("workflowProfile", LOCAL_WORKFLOW_PROFILE))
    if is_strict_workflow(workflow_profile):
        return True
    provider = _provider_for_registration_container(session["registration"])
    return generation_profile == getattr(provider, "nist_conformance_profile", None)


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
    settings = get_genval_settings()
    return {
        "provider": NIST_GENVAL_PROVIDER_ID,
        "providerName": NIST_GENVAL_PROVIDER_NAME,
        "runnerDll": str(settings.runner_dll),
        "artifactRoot": str(settings.artifact_root),
        "buildCommand": "scripts/nist/build_nist_genval.sh",
        "orleansCommand": "scripts/nist/start_orleans.sh",
    }


def _resolve_campaign_seed(
    provided_seed: Optional[str],
    registration_container: Dict[str, Any],
    provider: AcvpAlgorithmProvider,
) -> str:
    if provided_seed is None:
        fallback = getattr(provider, "fallback_campaign_seed", None)
        if not callable(fallback):
            raise AcvpSchemaError(
                "invalid_value",
                "Provider does not expose fallback campaign seed generation.",
                "$.campaignSeed",
            )
        return str(fallback(registration_container))
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


def _resolve_generation_profile(
    value: Optional[str],
    provider: AcvpAlgorithmProvider,
) -> str:
    profiles = list(getattr(provider, "generation_profiles", []))
    default_profile = getattr(provider, "default_generation_profile", None)
    if value is None:
        if isinstance(default_profile, str):
            return default_profile
        raise AcvpSchemaError(
            "invalid_value",
            "Provider does not expose a default generation profile.",
            "$.generationProfile",
        )
    if not isinstance(value, str):
        raise AcvpSchemaError(
            "invalid_type",
            "generationProfile must be a string",
            "$.generationProfile",
        )
    if value not in profiles:
        raise AcvpSchemaError(
            "invalid_value",
            "generationProfile must be one of: "
            + ", ".join(sorted(profiles)),
            "$.generationProfile",
        )
    return value


def _strict_generation_profile_if_needed(
    generation_profile: str,
    provider: AcvpAlgorithmProvider,
    *,
    workflow_profile: str,
    explicit_profile: bool,
) -> str:
    if explicit_profile or not is_strict_workflow(workflow_profile):
        return generation_profile
    nist_profile = getattr(provider, "nist_conformance_profile", None)
    if isinstance(nist_profile, str):
        return nist_profile
    return generation_profile


def _resolve_tests_per_group(
    value: Optional[int],
    generation_profile: str,
    provider: AcvpAlgorithmProvider,
) -> int:
    default_tests_per_group = getattr(provider, "default_tests_per_group", None)
    local_debug_profile = getattr(provider, "local_debug_profile", None)
    max_tests_per_group = getattr(provider, "max_tests_per_group", None)
    if value is None:
        if isinstance(default_tests_per_group, int):
            return default_tests_per_group
        raise AcvpSchemaError(
            "invalid_value",
            "Provider does not expose a default testsPerGroup.",
            "$.testsPerGroup",
        )
    if not isinstance(value, int) or isinstance(value, bool):
        raise AcvpSchemaError("invalid_type", "testsPerGroup must be an integer", "$.testsPerGroup")
    if value < 1:
        raise AcvpSchemaError(
            "invalid_value",
            "testsPerGroup must be at least 1",
            "$.testsPerGroup",
        )
    if (
        generation_profile == local_debug_profile
        and isinstance(max_tests_per_group, int)
        and value > max_tests_per_group
    ):
        raise AcvpSchemaError(
            "invalid_value",
            f"testsPerGroup must be between 1 and {max_tests_per_group}",
            "$.testsPerGroup",
        )
    return value


def _generation_profile_minimums(
    generation_profile: str,
    provider: AcvpAlgorithmProvider,
) -> Dict[str, int]:
    minimums = getattr(provider, "generation_profile_minimums", None)
    if callable(minimums):
        return dict(minimums(generation_profile))
    return {}


def _resolve_is_sample(value: Optional[bool], workflow_profile: str) -> bool:
    if value is not None:
        return bool(value)
    return not is_strict_workflow(workflow_profile)


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

    return with_skeleton_metadata(
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
    local_extension = body["extensions"]["localFips204Skeleton"]
    local_extension["vectorSets"] = page
    local_extension["query"] = body["query"]
    return with_skeleton_metadata(body)


def get_vector_set(
    vector_set_id: str,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    vector_set = get_vector_set_or_404(vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    path = f"/acvp/v1/vectorSets/{vector_set_id}"
    return _get_vector_set_prompt_response(vector_set, path, workflow_profile=workflow_profile)


def get_vector_set_prompt(
    session_id: str,
    vector_set_id: str,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    return _get_vector_set_prompt_response(
        vector_set,
        _nested_vector_set_path(session_id, vector_set_id),
        workflow_profile=workflow_profile,
    )


def _get_vector_set_prompt_response(
    vector_set: Dict[str, Any],
    path: str,
    *,
    workflow_profile: str,
) -> Any:
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if vector_set["status"] == VectorSetStatus.CREATED.value:
        return acvp_skeleton_error(
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

    if is_strict_workflow(workflow_profile):
        return vector_set["prompt"]

    return with_skeleton_metadata(
        {
            "vectorSetId": vector_set["vectorSetId"],
            "testSessionId": vector_set["testSessionId"],
            "status": vector_set["status"],
            "prompt": vector_set["prompt"],
            "generatedFromCapabilities": vector_set.get("generatedFromCapabilities", False),
            "generationProfile": vector_set.get("generationProfile"),
            "campaignSeed": vector_set.get("campaignSeed"),
            "isSample": _vector_set_is_sample(vector_set),
            "downloadedAt": vector_set.get("downloadedAt"),
            "expiresAt": vector_set.get("expiresAt"),
            "stateHistory": list(vector_set.get("stateHistory", [])),
        }
    )


def get_vector_set_expected_results(
    vector_set_id: str,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    vector_set = get_vector_set_or_404(vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    path = f"/acvp/v1/vectorSets/{vector_set_id}/expectedResults"
    return _get_vector_set_expected_response(
        vector_set,
        path,
        workflow_profile=workflow_profile,
    )


def get_vector_set_expected(
    session_id: str,
    vector_set_id: str,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
    return _get_vector_set_expected_response(
        vector_set,
        f"{_nested_vector_set_path(session_id, vector_set_id)}/expected",
        workflow_profile=workflow_profile,
    )


def _get_vector_set_expected_response(
    vector_set: Dict[str, Any],
    path: str,
    *,
    workflow_profile: str,
) -> Any:
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if vector_set["expectedResults"] is None:
        return acvp_skeleton_error(
            409,
            "EXPECTED_RESULTS_NOT_READY",
            "Expected results are not available for this local skeleton vector set.",
            path,
        )

    if is_strict_workflow(workflow_profile):
        if not _vector_set_is_sample(vector_set):
            return acvp_skeleton_error(
                403,
                "EXPECTED_RESULTS_NOT_AVAILABLE_FOR_NON_SAMPLE",
                "Expected results are not downloadable for non-sample vector sets.",
                path,
            )
        return vector_set["expectedResults"]

    return with_skeleton_metadata(
        {
            "vectorSetId": vector_set["vectorSetId"],
            "testSessionId": vector_set["testSessionId"],
            "expectedResults": vector_set["expectedResults"],
            "status": vector_set["status"],
            "isSample": _vector_set_is_sample(vector_set),
            "expiresAt": vector_set.get("expiresAt"),
            "localSkeletonExpectedEndpoint": True,
        }
    )


def submit_vector_set_results(
    session_id: Optional[str],
    vector_set_id: str,
    response: Any,
    *,
    show_expected: bool = False,
    update: bool = False,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    if session_id is None:
        vector_set = get_vector_set_or_404(vector_set_id)
        path = f"/acvp/v1/vectorSets/{vector_set_id}/results"
    else:
        vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
        path = f"{_nested_vector_set_path(session_id, vector_set_id)}/results"
    if isinstance(vector_set, JSONResponse):
        return vector_set
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
        return acvp_skeleton_error(
            409,
            "VECTOR_SET_NOT_READY",
            "Vector set is not ready for result submission.",
            path,
        )
    session = get_acvp_session(vector_set["testSessionId"])
    if session is not None and session.get("submittedForValidation"):
        return acvp_skeleton_error(
            409,
            "VECTOR_SET_ALREADY_FINALIZED",
            "Vector set results cannot be changed after session submit-for-validation.",
            path,
        )
    if vector_set["expectedResults"] is None:
        return acvp_skeleton_error(
            409,
            "EXPECTED_RESULTS_NOT_READY",
            "Expected results must be generated before result submission in the local skeleton.",
            path,
        )

    response = _response_with_prompt_metadata(response, vector_set)
    mode = normalize_acvp_json(vector_set["prompt"]).get("mode")
    try:
        provider = _provider_for_prompt(vector_set["prompt"])
        provider.validate_response(response, expected_mode=mode)
        if _vector_set_uses_nist_genval(vector_set):
            validation_result = _validate_with_nist_genval(vector_set, response)
        else:
            validation_result = provider.validate_results(
                prompt=vector_set["prompt"],
                expected_results=vector_set["expectedResults"],
                response=response,
            )
        report = build_report(vector_set_id, validation_result)
    except AcvpSchemaError as exc:
        return acvp_skeleton_error(400, exc.code, exc.message, exc.path)
    except GenValConfigurationError as exc:
        return acvp_skeleton_error(
            500,
            "NIST_GENVAL_NOT_READY",
            str(exc),
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValArtifactError as exc:
        return acvp_skeleton_error(
            500,
            "NIST_GENVAL_ARTIFACT_MISSING",
            str(exc),
            "$",
            details=_nist_genval_error_details(),
        )
    except GenValExecutionError as exc:
        return acvp_skeleton_error(
            500,
            "NIST_GENVAL_EXECUTION_ERROR",
            str(exc),
            "$",
            details=_nist_genval_error_details(),
        )
    except ValueError as exc:
        return acvp_skeleton_error(400, "VALIDATION_ERROR", str(exc), "$")

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
                metadata={"vectorSetId": vector_set_id},
            )
        _transition_vector_if_needed(
            vector_set,
            VectorSetStatus.VALIDATING.value,
            reason="Vector set results are being synchronously validated.",
        )
        vector_set["validatingAt"] = vector_set["updatedAt"]
        vector_set["response"] = response
        vector_set["validationResult"] = validation_result
        vector_set["report"] = report
        vector_set["showExpected"] = bool(show_expected)
        _transition_vector_if_needed(
            vector_set,
            final_status,
            reason=(
                "Vector set results validated by NIST GenVal."
                if _vector_set_uses_nist_genval(vector_set)
                else "Vector set results validated by local skeleton validator."
            ),
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
        expected_results=vector_set["expectedResults"],
        show_expected=bool(show_expected),
    )
    vector_set["acvpResults"] = acvp_results
    save_acvp_vector_set(vector_set)

    if is_strict_workflow(workflow_profile):
        from fastapi import Response

        return Response(status_code=204)

    return _vector_set_results_response(
        vector_set,
        acvp_results,
        validation_result=validation_result,
        report=report,
        submission_action="updated" if update else "submitted",
        local_put_replace_behavior=update,
        local_post_returns_results=not update,
    )


def get_vector_set_results(
    session_id: Optional[str],
    vector_set_id: str,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
    show_expected: bool = False,
) -> Any:
    if session_id is None:
        vector_set = get_vector_set_or_404(vector_set_id)
        path = f"/acvp/v1/vectorSets/{vector_set_id}/results"
    else:
        vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
        path = f"{_nested_vector_set_path(session_id, vector_set_id)}/results"
    if isinstance(vector_set, JSONResponse):
        return vector_set
    unavailable = _reject_if_vector_unavailable(vector_set, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if is_strict_workflow(workflow_profile) and show_expected and not _vector_set_is_sample(vector_set):
        return acvp_skeleton_error(
            403,
            "SHOW_EXPECTED_NOT_AVAILABLE_FOR_NON_SAMPLE",
            "showExpected is not available for strict non-sample vector sets.",
            path,
        )

    acvp_results = vector_set.get("acvpResults")
    if is_strict_workflow(workflow_profile):
        return build_acvp_vector_set_results(
            vector_set=vector_set,
            validation_result=vector_set.get("validationResult"),
            response=vector_set.get("response"),
            expected_results=vector_set.get("expectedResults"),
            show_expected=bool(show_expected),
        )

    if not isinstance(acvp_results, dict):
        acvp_results = build_acvp_vector_set_results(
            vector_set=vector_set,
            validation_result=vector_set.get("validationResult"),
            response=vector_set.get("response"),
            expected_results=vector_set.get("expectedResults"),
            show_expected=bool(vector_set.get("showExpected")),
        )
        vector_set["acvpResults"] = acvp_results
        save_acvp_vector_set(vector_set)

    return _vector_set_results_response(
        vector_set,
        acvp_results,
        validation_result=vector_set.get("validationResult"),
        report=vector_set.get("report"),
    )


def get_test_session_results(
    session_id: str,
    *,
    workflow_profile: str = LOCAL_WORKFLOW_PROFILE,
) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}/results"
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if not session["vectorSetIds"] and session["status"] == TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return acvp_skeleton_error(
            409,
            "VECTOR_SETS_NOT_GENERATED",
            "This registration session has no vector sets yet. Generate vector sets before requesting results.",
            path,
        )

    if is_strict_workflow(workflow_profile):
        return _strict_test_session_results(session)

    vector_results = []
    for vector_set_id in session["vectorSetIds"]:
        vector_set = get_acvp_vector_set(vector_set_id)
        if vector_set is None or vector_set["validationResult"] is None:
            continue
        vector_results.append(
            {
                "vectorSetId": vector_set_id,
                "status": vector_set["status"],
                "validationResult": vector_set["validationResult"],
                "report": vector_set["report"],
            }
        )

    if not vector_results:
        return acvp_skeleton_error(
            409,
            "RESULTS_NOT_SUBMITTED",
            "No vector set results have been submitted for this test session.",
            path,
        )

    return with_skeleton_metadata(
        {
            "testSessionId": session_id,
            "status": session["status"],
            "summary": _session_result_summary(session),
            "vectorSetResults": vector_results,
            "stateHistory": list(session.get("stateHistory", [])),
        }
    )


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
                "vectorSetUrl": _nested_vector_set_path(session["testSessionId"], vector_set_id),
                "status": disposition,
                "disposition": disposition,
            }
        )

    return {
        "passed": all_passed,
        "results": results,
    }


def submit_test_session_for_validation(session_id: str) -> Any:
    session = _get_session(session_id)
    if isinstance(session, JSONResponse):
        return session
    path = f"/acvp/v1/testSessions/{session_id}/submit"
    unavailable = _reject_if_session_unavailable(session, path)
    if isinstance(unavailable, JSONResponse):
        return unavailable
    if not session["vectorSetIds"] and session["status"] == TestSessionStatus.CAPABILITIES_ACCEPTED.value:
        return acvp_skeleton_error(
            409,
            "VECTOR_SETS_NOT_GENERATED",
            "This registration session has no vector sets yet. Generate vector sets before session submit.",
            path,
        )

    summary = _session_result_summary(session)
    if summary["submittedVectorSets"] == 0:
        return acvp_skeleton_error(
            409,
            "RESULTS_NOT_SUBMITTED",
            "No vector set results have been submitted for this test session.",
            path,
        )
    if summary["pendingVectorSets"] > 0:
        return acvp_skeleton_error(
            409,
            "VECTOR_SET_RESULTS_INCOMPLETE",
            "All vector set results must be submitted before session-level validation.",
            path,
        )

    if not session.get("submittedForValidation"):
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
        session["submittedForValidation"] = True
        session["submittedForValidationAt"] = session["updatedAt"]
        save_acvp_session(session)
        summary = _session_result_summary(session)

    return with_skeleton_metadata(
        {
            "testSessionId": session_id,
            "status": session["status"],
            "summary": summary,
            "submittedForValidation": session.get("submittedForValidation", False),
            "submittedForValidationAt": session.get("submittedForValidationAt"),
            "stateHistory": list(session.get("stateHistory", [])),
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

    return with_skeleton_metadata(
        {
            "cancelled": True,
            "testSessionId": session_id,
            "status": session["status"],
            "localSkeletonBehavior": True,
            "stateHistory": list(session.get("stateHistory", [])),
        }
    )


def cancel_vector_set(session_id: Optional[str], vector_set_id: str) -> Any:
    if session_id is None:
        vector_set = get_vector_set_or_404(vector_set_id)
        path = f"/acvp/v1/vectorSets/{vector_set_id}"
    else:
        vector_set = get_vector_set_for_session_or_404(session_id, vector_set_id)
        path = _nested_vector_set_path(session_id, vector_set_id)
    if isinstance(vector_set, JSONResponse):
        return vector_set
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

    return with_skeleton_metadata(
        {
            "cancelled": vector_set["status"] == VectorSetStatus.CANCELLED.value,
            "vectorSetId": vector_set_id,
            "testSessionId": vector_set["testSessionId"],
            "status": vector_set["status"],
            "localSkeletonBehavior": True,
            "stateHistory": list(vector_set.get("stateHistory", [])),
        }
    )


def get_session_or_404(session_id: str) -> Any:
    session = get_acvp_session(session_id)
    if session is None:
        return acvp_skeleton_error(
            404,
            "UNKNOWN_TEST_SESSION",
            "Unknown testSessionId.",
            f"/acvp/v1/testSessions/{session_id}",
        )
    return session


def get_vector_set_or_404(vector_set_id: str) -> Any:
    vector_set = get_acvp_vector_set(vector_set_id)
    if vector_set is None:
        return acvp_skeleton_error(
            404,
            "UNKNOWN_VECTOR_SET",
            "Unknown vectorSetId.",
            f"/acvp/v1/vectorSets/{vector_set_id}",
        )
    return vector_set


def get_vector_set_for_session_or_404(session_id: str, vector_set_id: str) -> Any:
    session = get_session_or_404(session_id)
    if isinstance(session, JSONResponse):
        return session
    vector_set = get_acvp_vector_set(vector_set_id)
    if vector_set is None or vector_set.get("testSessionId") != session_id:
        return acvp_skeleton_error(
            404,
            "UNKNOWN_VECTOR_SET",
            "Unknown vectorSetId for test session.",
            _nested_vector_set_path(session_id, vector_set_id),
        )
    return vector_set


def _get_session(session_id: str) -> Any:
    return get_session_or_404(session_id)


def _get_vector_set(vector_set_id: str) -> Any:
    return get_vector_set_or_404(vector_set_id)


def _session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    vector_set_summaries = [
        _vector_set_summary(vector_set)
        for vector_set_id in session["vectorSetIds"]
        for vector_set in [get_acvp_vector_set(vector_set_id)]
        if vector_set is not None
    ]
    first_summary = vector_set_summaries[0] if vector_set_summaries else {}
    result_summary = _session_result_summary(session)
    summary = {
        "testSessionId": session["testSessionId"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "expiresAt": session.get("expiresAt"),
        "status": session["status"],
        "label": session.get("label"),
        "vectorSetIds": list(session["vectorSetIds"]),
        "vectorSetUrls": list(session["vectorSetUrls"]),
        "vectorSetCount": len(session["vectorSetIds"]),
        "downloadedVectorSetCount": result_summary["downloadedVectorSets"],
        "submittedVectorSetCount": result_summary["submittedVectorSets"],
        "validatedVectorSetCount": result_summary["validatedVectorSets"],
        "failedVectorSetCount": result_summary["failedVectorSets"],
        "pendingVectorSetCount": result_summary["pendingVectorSets"],
        "algorithm": first_summary.get("algorithm"),
        "mode": first_summary.get("mode"),
        "revision": first_summary.get("revision"),
        "testGroupCount": first_summary.get("testGroupCount", 0),
        "testCaseCount": first_summary.get("testCaseCount", 0),
        "stateHistory": list(session.get("stateHistory", [])),
        **SKELETON_METADATA,
    }
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
    return {
        "vectorSetId": vector_set["vectorSetId"],
        "testSessionId": vector_set["testSessionId"],
        "status": vector_set["status"],
        "url": _nested_vector_set_path(
            vector_set["testSessionId"],
            vector_set["vectorSetId"],
        ),
        "generatedFromCapabilities": vector_set.get("generatedFromCapabilities", False),
        "generationProfile": vector_set.get("generationProfile"),
        "campaignSeed": vector_set.get("campaignSeed"),
        "provider": vector_set.get("provider"),
        "providerName": vector_set.get("providerName"),
        "expectedResultsDebugOnly": vector_set.get("expectedResultsDebugOnly", False),
        "hasInternalProjection": vector_set.get("hasInternalProjection", False),
        "nistSourceCommit": vector_set.get("nistSourceCommit"),
        "mode": vector_set.get("mode", prompt_summary.get("mode")),
        "vsId": vector_set.get("vsId", prompt_summary.get("vsId")),
        "downloadedAt": vector_set.get("downloadedAt"),
        "submittedAt": vector_set.get("submittedAt"),
        "validatedAt": vector_set.get("validatedAt"),
        "failedAt": vector_set.get("failedAt"),
        "cancelledAt": vector_set.get("cancelledAt"),
        "expiresAt": vector_set.get("expiresAt"),
        "stateHistory": list(vector_set.get("stateHistory", [])),
        **prompt_summary,
        **SKELETON_METADATA,
    }


def _nested_vector_set_path(session_id: str, vector_set_id: str) -> str:
    return f"/acvp/v1/testSessions/{session_id}/vectorSets/{vector_set_id}"


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


def _vector_set_uses_nist_genval(vector_set: Dict[str, Any]) -> bool:
    return vector_set.get("provider") == NIST_GENVAL_PROVIDER_ID


def _validate_with_nist_genval(
    vector_set: Dict[str, Any],
    response: Any,
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

    validation_result = normalize_nist_validation(
        validation_payload,
        prompt=vector_set["prompt"],
    )
    validation_result["metadata"]["providerName"] = NIST_GENVAL_PROVIDER_NAME
    validation_result["metadata"]["expectedResultsDebugOnly"] = True
    validation_result["metadata"]["validationArtifact"] = str(validation_path)
    return validation_result


def _vector_set_results_response(
    vector_set: Dict[str, Any],
    acvp_results: Dict[str, Any],
    *,
    validation_result: Optional[Dict[str, Any]] = None,
    report: Optional[Dict[str, Any]] = None,
    submission_action: Optional[str] = None,
    local_put_replace_behavior: bool = False,
    local_post_returns_results: bool = False,
) -> Dict[str, Any]:
    local_extension: Dict[str, Any] = {
        **SKELETON_METADATA,
        "vectorSetId": vector_set["vectorSetId"],
        "testSessionId": vector_set["testSessionId"],
        "status": vector_set["status"],
        "showExpected": bool(vector_set.get("showExpected")),
        "stateHistory": list(vector_set.get("stateHistory", [])),
        "provider": vector_set.get("provider"),
        "providerName": vector_set.get("providerName"),
        "expectedResultsDebugOnly": vector_set.get("expectedResultsDebugOnly", False),
        "hasInternalProjection": vector_set.get("hasInternalProjection", False),
        "nistSourceCommit": vector_set.get("nistSourceCommit"),
    }
    if submission_action is not None:
        local_extension["submissionAction"] = submission_action
    if local_put_replace_behavior:
        local_extension["localPutReplaceBehavior"] = True
        local_extension["localSkeletonPutReplaceBehavior"] = True
    if local_post_returns_results:
        local_extension["localPostReturnsResults"] = True
    if validation_result is not None:
        local_extension["validationResult"] = validation_result
    if report is not None:
        local_extension["report"] = report

    body = {
        **acvp_results,
        "extensions": {"localFips204Skeleton": local_extension},
    }
    return with_skeleton_metadata(body)


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
        return acvp_skeleton_error(
            409,
            "TEST_SESSION_EXPIRED",
            "Test session has expired in the local skeleton state machine.",
            path,
        )
    if session["status"] == TestSessionStatus.CANCELLED.value and not allow_cancelled:
        return acvp_skeleton_error(
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
        return acvp_skeleton_error(
            409,
            "VECTOR_SET_EXPIRED",
            "Vector set has expired in the local skeleton state machine.",
            path,
        )
    if vector_set["status"] == VectorSetStatus.CANCELLED.value and not allow_cancelled:
        return acvp_skeleton_error(
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
    return acvp_skeleton_error(409, exc.code, exc.message, exc.path)


def _validate_status_filter(
    status: Optional[str],
    *,
    allowed: set,
    entity: str,
) -> Optional[JSONResponse]:
    if status is None:
        return None
    if status not in allowed:
        return acvp_skeleton_error(
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
