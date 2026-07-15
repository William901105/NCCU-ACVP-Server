from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .common import require_bool, require_int
from .constants import ALGORITHM, REVISION
from .validators import validate_mlkem_registration


def map_mlkem_registration_to_nist(
    registration: Dict[str, Any],
    *,
    vs_id: int,
    is_sample: bool = True,
) -> Dict[str, Any]:
    normalized = validate_mlkem_registration(registration)
    mapped: Dict[str, Any] = {
        "vsId": require_int(vs_id, "$.vsId"),
        "algorithm": ALGORITHM,
        "mode": normalized["mode"],
        "revision": REVISION,
        "isSample": require_bool(is_sample, "$.isSample"),
        "parameterSets": list(normalized["parameterSets"]),
    }
    if normalized["mode"] == "encapDecap":
        mapped["functions"] = list(normalized["functions"])
    if "prereqVals" in normalized:
        mapped["prereqVals"] = deepcopy(normalized["prereqVals"])
    return mapped
