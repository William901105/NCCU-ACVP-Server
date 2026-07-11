# ML-DSA Schema Boundary

The ML-DSA schema layer validates the registration container, NIST prompt, and
IUT response used by the strict ACVP workflow. It is aligned with the NIST
ACVP ML-DSA draft:

<https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html>

Supported combinations are ML-DSA `keyGen`, `sigGen`, and `sigVer` with
revision `FIPS204`. Schema errors retain structured JSON paths so registration
and response failures can be reported as ACVP error envelopes.

The schema layer is an internal provider responsibility, not a separate public
validation API. Strict session creation validates the registration before
calling NIST GenVal; prompt and response validation guard the corresponding
NIST artifact and IUT-result boundaries. NIST GenVal, rather than this schema
layer, determines cryptographic results and final dispositions.

The test fixtures under `tests/fixtures/nist/mldsa/` cover prompts, expected
results, and pass/fail IUT responses for every supported mode. They are used by
the fixture-backed NIST test provider and are not exposed through application
routes.
