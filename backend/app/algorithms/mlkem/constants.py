from __future__ import annotations


ALGORITHM = "ML-KEM"
REVISION = "FIPS203"
# FIPS203-tr1 is an ACVP *test* revision (test revision 1) against the same
# FIPS 203 standard. It adds the keyFormats capability (seed / expanded private
# key formats) to encapDecap. See docs/mlkem-fips203-tr1-spec.md.
REVISION_TR1 = "FIPS203-tr1"
REVISIONS = {REVISION, REVISION_TR1}

# Registrable private-key formats, applicable only to
# ML-KEM / encapDecap / FIPS203-tr1 (the formats an IUT may advertise).
KEY_FORMATS = {"expanded", "seed"}
# Per-testGroup keyFormat values understood by the pinned GenVal schemas.
# Decapsulation carries "seed" or "expanded". Fresh generation currently leaves
# key-check/non-private groups at the enum default "none"; the corrected official
# decapsulationKeyCheck fixture instead carries "expanded" plus dk.
GROUP_KEY_FORMATS = {"none", "seed", "expanded"}
# The seed key format carries the decapsulation key as separate d(32) and z(32)
# fields (not a single concatenated seed); the IUT expands them to the dk.

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
