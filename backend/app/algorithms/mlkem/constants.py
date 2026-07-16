from __future__ import annotations


ALGORITHM = "ML-KEM"
REVISION = "FIPS203"

MODES = {"keyGen", "encapDecap"}
PARAMETER_SETS = {"ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"}
FUNCTIONS = {
    "encapsulation",
    "decapsulation",
    "encapsulationKeyCheck",
    "decapsulationKeyCheck",
}
TEST_TYPES = {"AFT", "VAL"}
PREREQUISITE_ALGORITHMS = {"SHA", "DRBG"}

FUNCTION_TEST_TYPES = {
    "keyGen": "AFT",
    "encapsulation": "AFT",
    "decapsulation": "VAL",
    "encapsulationKeyCheck": "VAL",
    "decapsulationKeyCheck": "VAL",
}

D_BYTES = 32
Z_BYTES = 32
M_BYTES = 32
K_BYTES = 32

ENCAPSULATION_KEY_BYTES = {
    "ML-KEM-512": 800,
    "ML-KEM-768": 1184,
    "ML-KEM-1024": 1568,
}

DECAPSULATION_KEY_BYTES = {
    "ML-KEM-512": 1632,
    "ML-KEM-768": 2400,
    "ML-KEM-1024": 3168,
}

CIPHERTEXT_BYTES = {
    "ML-KEM-512": 768,
    "ML-KEM-768": 1088,
    "ML-KEM-1024": 1568,
}
