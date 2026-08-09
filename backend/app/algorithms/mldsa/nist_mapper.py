from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .constants import ALGORITHM, REVISION
from .validators import validate_mldsa_registration


def map_mldsa_registration_to_nist(
    registration: Dict[str, Any],
    *,
    vs_id: int,
    is_sample: bool = True,
    revision: str = REVISION,
) -> Dict[str, Any]:
    normalized = validate_mldsa_registration(registration, revision=revision)
    mode = normalized["mode"]
    mapped: Dict[str, Any] = {
        "vsId": vs_id,
        "algorithm": ALGORITHM,
        "mode": mode,
        "revision": normalized["revision"],
        "isSample": bool(is_sample),
    }

    if mode == "keyGen":
        mapped["parameterSets"] = list(normalized["parameterSets"])
        return mapped

    mapped["capabilities"] = deepcopy(normalized["capabilities"])
    mapped["signatureInterfaces"] = list(normalized["signatureInterfaces"])

    if mode == "sigGen":
        mapped["deterministic"] = list(normalized["deterministic"])
        if "keyFormats" in normalized:
            mapped["keyFormats"] = list(normalized["keyFormats"])

    if "internal" in normalized["signatureInterfaces"]:
        mapped["externalMu"] = list(normalized["externalMu"])
    if "external" in normalized["signatureInterfaces"]:
        mapped["preHash"] = list(normalized["preHash"])
    return mapped
