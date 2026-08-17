from __future__ import annotations

from ...acvp_core.algorithm_descriptor import AlgorithmDescriptor
from ...acvp_core.algorithm_identity import AlgorithmIdentity


MLKEM_NIST_REFERENCES = (
    "https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html",
    "https://csrc.nist.gov/pubs/fips/203/final",
)


def build_mlkem_descriptor() -> AlgorithmDescriptor:
    return AlgorithmDescriptor(
        provider_id="nist-ml-kem-fips203",
        algorithm="ML-KEM",
        revision="FIPS203",
        display_name="ML-KEM (FIPS 203)",
        enabled=True,
        modes=("keyGen", "encapDecap"),
        parameter_sets=("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"),
        registration_schema_version="draft-celi-acvp-ml-kem-01",
        response_schema_version="draft-celi-acvp-ml-kem-01",
        execution_backend="nist-genval",
        nist_references=MLKEM_NIST_REFERENCES,
        supported_identities=(
            AlgorithmIdentity("ML-KEM", "keyGen", "FIPS203"),
            AlgorithmIdentity("ML-KEM", "encapDecap", "FIPS203"),
        ),
        capability_metadata={
            "functions": [
                "encapsulation",
                "decapsulation",
                "encapsulationKeyCheck",
                "decapsulationKeyCheck",
            ],
            "testTypes": {
                "keyGen": ["AFT"],
                "encapsulation": ["AFT"],
                "decapsulation": ["VAL"],
                "encapsulationKeyCheck": ["VAL"],
                "decapsulationKeyCheck": ["VAL"],
            },
        },
    )
