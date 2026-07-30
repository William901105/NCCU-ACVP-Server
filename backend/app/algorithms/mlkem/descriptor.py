from __future__ import annotations

from ...acvp_core.algorithm_descriptor import AlgorithmDescriptor


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


def build_mlkem_tr1_descriptor() -> AlgorithmDescriptor:
    """ML-KEM / encapDecap / FIPS203-tr1.

    Test revision 1 of the encapDecap testing against the same FIPS 203
    standard; adds the keyFormats capability (seed / expanded private key
    formats). keyGen remains under the FIPS203 revision.
    """
    return AlgorithmDescriptor(
        provider_id="nist-ml-kem-fips203-tr1",
        algorithm="ML-KEM",
        revision="FIPS203-tr1",
        display_name="ML-KEM (FIPS 203, test revision 1)",
        enabled=True,
        modes=("encapDecap",),
        parameter_sets=("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"),
        registration_schema_version="draft-celi-acvp-ml-kem-01",
        response_schema_version="draft-celi-acvp-ml-kem-01",
        execution_backend="nist-genval",
        nist_references=MLKEM_NIST_REFERENCES,
        capability_metadata={
            "functions": [
                "encapsulation",
                "decapsulation",
                "encapsulationKeyCheck",
                "decapsulationKeyCheck",
            ],
            "keyFormats": ["expanded", "seed"],
            "testTypes": {
                "encapsulation": ["AFT"],
                "decapsulation": ["VAL"],
                "encapsulationKeyCheck": ["VAL"],
                "decapsulationKeyCheck": ["VAL"],
            },
        },
    )
