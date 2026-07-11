from __future__ import annotations

from ...acvp_core.algorithm_descriptor import AlgorithmDescriptor


MLDSA_NIST_REFERENCES = (
    "https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html",
    "https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html",
    "https://csrc.nist.gov/pubs/fips/204/final",
)


def build_mldsa_descriptor() -> AlgorithmDescriptor:
    return AlgorithmDescriptor(
        provider_id="nist-ml-dsa-fips204",
        algorithm="ML-DSA",
        revision="FIPS204",
        display_name="ML-DSA (FIPS 204)",
        enabled=True,
        modes=("keyGen", "sigGen", "sigVer"),
        parameter_sets=("ML-DSA-44", "ML-DSA-65", "ML-DSA-87"),
        registration_schema_version="draft-celi-acvp-ml-dsa-01",
        response_schema_version="draft-celi-acvp-ml-dsa-01",
        execution_backend="nist-genval",
        nist_references=MLDSA_NIST_REFERENCES,
        capability_metadata={
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
        },
    )
