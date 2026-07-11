from __future__ import annotations

from typing import Dict, Set, Tuple


# Aligned with NIST ACVP ML-DSA draft-celi-acvp-ml-dsa-01.
ALGORITHM = "ML-DSA"
REVISION = "FIPS204"

MODES: Set[str] = {"keyGen", "sigGen", "sigVer"}
PARAMETER_SETS: Set[str] = {"ML-DSA-44", "ML-DSA-65", "ML-DSA-87"}
TEST_TYPES: Set[str] = {"AFT"}

SIGNATURE_INTERFACES: Set[str] = {"internal", "external"}
PRE_HASH_VALUES: Set[str] = {"pure", "preHash"}
HASH_ALGORITHMS: Set[str] = {
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
}

HASH_ALGORITHM_DIGEST_BYTES: Dict[str, int] = {
    "SHA2-224": 28,
    "SHA2-256": 32,
    "SHA2-384": 48,
    "SHA2-512": 64,
    "SHA2-512/224": 28,
    "SHA2-512/256": 32,
    "SHA3-224": 28,
    "SHA3-256": 32,
    "SHA3-384": 48,
    "SHA3-512": 64,
    "SHAKE-128": 32,
    "SHAKE-256": 64,
}

MODE_ALIASES: Dict[str, str] = {
    "keygen": "keyGen",
    "keyGen": "keyGen",
    "keyGen".lower(): "keyGen",
    "siggen": "sigGen",
    "sigGen": "sigGen",
    "sigGen".lower(): "sigGen",
    "sigver": "sigVer",
    "sigVer": "sigVer",
    "sigVer".lower(): "sigVer",
}

REGISTRATION_REQUIRED_BY_MODE: Dict[str, Set[str]] = {
    "keyGen": {"parameterSets"},
    "sigGen": {"capabilities", "deterministic", "signatureInterfaces"},
    "sigVer": {"capabilities", "signatureInterfaces"},
}

PUBLIC_KEY_BYTES: Dict[str, int] = {
    "ML-DSA-44": 1312,
    "ML-DSA-65": 1952,
    "ML-DSA-87": 2592,
}

SECRET_KEY_BYTES: Dict[str, int] = {
    "ML-DSA-44": 2560,
    "ML-DSA-65": 4032,
    "ML-DSA-87": 4896,
}

SIGNATURE_BYTES: Dict[str, int] = {
    "ML-DSA-44": 2420,
    "ML-DSA-65": 3309,
    "ML-DSA-87": 4627,
}

SEED_BYTES = 32
RND_BYTES = 32
MU_BYTES = 64
CONTEXT_MAX_BYTES = 255

DOMAIN_CONSTRAINTS: Dict[str, Tuple[int, int, int]] = {
    # Bit lengths, per the ACVP ML-DSA capability registration tables.
    "messageLength": (8, 65536, 8),
    "contextLength": (0, 2040, 8),
}
