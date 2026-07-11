from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List

from fastapi.responses import JSONResponse

from app.acvp_mldsa.expected import generate_expected_results_from_prompt
from app.acvp_mldsa.validators import validate_mldsa_response, validate_mldsa_vector_set
from app.acvp_protocol.capabilities import (
    negotiate_mldsa_capabilities,
    validate_registration_container,
)
from app.acvp_protocol.routes import create_acvp_v1_test_session, get_acvp_v1_algorithms
from app.acvp_protocol.service import (
    ACVP_SKELETON_SESSION_STORE,
    ACVP_SKELETON_VECTOR_SET_STORE,
)
from app.acvp_protocol.vector_generation import generate_vector_sets_from_negotiated_capabilities
from app.crypto_oracle.mldsa_helpers import hash_message_for_prehash
from app.validator import validate


CAMPAIGN_SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"
MESSAGE_HEX = "00010203040506070809"
SHAKE_ALGS = ["SHAKE-128", "SHAKE-256"]


def setup_function() -> None:
    ACVP_SKELETON_SESSION_STORE.clear()
    ACVP_SKELETON_VECTOR_SET_STORE.clear()


def test_shake_digest_mapping_matches_native_wrapper_lengths() -> None:
    message = bytes.fromhex(MESSAGE_HEX)

    assert hash_message_for_prehash(MESSAGE_HEX, "SHAKE-128") == (
        hashlib.shake_128(message).digest(32).hex().upper()
    )
    assert hash_message_for_prehash(MESSAGE_HEX, "SHAKE-256") == (
        hashlib.shake_256(message).digest(64).hex().upper()
    )


def test_registration_with_shake_128_and_256_is_negotiated() -> None:
    negotiated = negotiate_mldsa_capabilities(
        validate_registration_container(
            {"algorithms": [_siggen_registration(SHAKE_ALGS)]}
        )
    )

    entry = negotiated["negotiated"][0]
    assert entry["hashAlgs"] == SHAKE_ALGS
    assert negotiated["warnings"] == []
    assert negotiated["unsupported"] == []


def test_acvp_v1_algorithms_advertises_shake_generation_support() -> None:
    response = _body_of(get_acvp_v1_algorithms())
    entry = response["algorithms"][0]

    assert "SHAKE-128" in entry["external"]["hashAlgs"]
    assert "SHAKE-256" in entry["external"]["hashAlgs"]
    assert entry["workflowPolicy"] == "strict"
    assert entry["executionBackend"] == "nist-genval"


def test_siggen_external_prehash_shake_expected_results_are_generated() -> None:
    prompt = _generate(_siggen_registration(SHAKE_ALGS))[0]

    validate_mldsa_vector_set(prompt)
    assert _hash_algs_in_prompt(prompt) == set(SHAKE_ALGS)

    expected = generate_expected_results_from_prompt(prompt)
    validate_mldsa_response(expected, expected_mode="sigGen")


def test_sigver_external_prehash_shake_expected_results_and_matching_response() -> None:
    prompt = _generate(_sigver_registration(SHAKE_ALGS))[0]

    validate_mldsa_vector_set(prompt)
    assert _hash_algs_in_prompt(prompt) == set(SHAKE_ALGS)

    expected = generate_expected_results_from_prompt(prompt)
    validate_mldsa_response(expected, expected_mode="sigVer")

    result = validate(
        {
            "prompt": prompt,
            "expectedResults": expected,
            "response": copy.deepcopy(expected),
        }
    )

    assert result["summary"]["failed"] == 0


def test_route_generation_accepts_only_shake_prehash_registration() -> None:
    response = _body_of(
        create_acvp_v1_test_session(
            {
                "algorithms": [_siggen_registration(["SHAKE-256"])],
                "campaignSeed": CAMPAIGN_SEED,
            }
        )
    )

    assert response["status"] == "vectorReady"
    assert response["negotiationWarnings"] == []
    vector_set = ACVP_SKELETON_VECTOR_SET_STORE[response["vectorSetIds"][0]]
    assert _hash_algs_in_prompt(vector_set["prompt"]) == {"SHAKE-256"}


def _generate(registration: Dict[str, Any]) -> List[Dict[str, Any]]:
    negotiated = negotiate_mldsa_capabilities(
        validate_registration_container({"algorithms": [registration]})
    )
    return generate_vector_sets_from_negotiated_capabilities(
        negotiated,
        campaign_seed=CAMPAIGN_SEED,
        tests_per_group=1,
    )


def _siggen_registration(hash_algs: List[str]) -> Dict[str, Any]:
    return {
        "algorithm": "ML-DSA",
        "mode": "sigGen",
        "revision": "FIPS204",
        "deterministic": [True],
        "signatureInterfaces": ["external"],
        "preHash": ["preHash"],
        "capabilities": [_capability(hash_algs)],
    }


def _sigver_registration(hash_algs: List[str]) -> Dict[str, Any]:
    return {
        "algorithm": "ML-DSA",
        "mode": "sigVer",
        "revision": "FIPS204",
        "signatureInterfaces": ["external"],
        "preHash": ["preHash"],
        "capabilities": [_capability(hash_algs)],
    }


def _capability(hash_algs: List[str]) -> Dict[str, Any]:
    return {
        "parameterSets": ["ML-DSA-44"],
        "messageLength": [{"min": 8, "max": 128, "increment": 8}],
        "contextLength": [{"min": 0, "max": 64, "increment": 8}],
        "hashAlgs": hash_algs,
    }


def _hash_algs_in_prompt(prompt: Dict[str, Any]) -> set[str]:
    return {
        test["hashAlg"]
        for group in prompt["testGroups"]
        for test in group["tests"]
        if "hashAlg" in test
    }


def _body_of(value: Any) -> Dict[str, Any]:
    if isinstance(value, JSONResponse):
        value = json.loads(value.body.decode("utf-8"))
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], dict)
        and value[0].get("acvVersion") == "1.0"
    ):
        return value[1]
    return value
