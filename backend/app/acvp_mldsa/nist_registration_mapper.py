from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .constants import ALGORITHM, REVISION
from .validators import validate_mldsa_registration


def map_mldsa_registration_to_nist(
    registration: Dict[str, Any],
    *,
    vs_id: int,
    is_sample: bool = True,
) -> Dict[str, Any]:
    normalized = validate_mldsa_registration(registration)
    mode = normalized["mode"]
    mapped: Dict[str, Any] = {
        "vsId": vs_id,
        "algorithm": ALGORITHM,
        "mode": mode,
        "revision": REVISION,
        "isSample": bool(is_sample),
    }

    if mode == "keyGen":
        mapped["parameterSets"] = list(normalized["parameterSets"])
        return mapped

    mapped["capabilities"] = deepcopy(normalized["capabilities"])
    mapped["signatureInterfaces"] = list(normalized["signatureInterfaces"])

    if mode == "sigGen":
        mapped["deterministic"] = list(normalized["deterministic"])

    if "internal" in normalized["signatureInterfaces"]:
        mapped["externalMu"] = list(normalized["externalMu"])
    if "external" in normalized["signatureInterfaces"]:
        mapped["preHash"] = list(normalized["preHash"])
    return mapped


def map_mldsa_registration_container_to_nist(
    container: Dict[str, Any],
    *,
    is_sample: bool = True,
    starting_vs_id: int = 1,
) -> List[Dict[str, Any]]:
    registrations = container.get("algorithms")
    if not isinstance(registrations, list) or not registrations:
        raise ValueError("registration container must include a non-empty algorithms array")
    return [
        map_mldsa_registration_to_nist(
            registration,
            vs_id=starting_vs_id + index,
            is_sample=is_sample,
        )
        for index, registration in enumerate(registrations)
    ]
