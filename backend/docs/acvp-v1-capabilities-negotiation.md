# ACVP v1 Capabilities Negotiation

Phase 3-3 added a local ML-DSA registration/capabilities negotiation layer for the `/acvp/v1` skeleton. Phase 3-4 can use the negotiated plan to generate deterministic local vector sets, Phase 3-5 attaches those sessions to the local state machine, and the current implementation persists them in PostgreSQL. This remains based on the NIST ACVP Protocol Specification registration/capabilities exchange model and the NIST ACVP ML-DSA JSON Specification, and it is still not a production-ready ACVP server.

References:

- ACVP Protocol Specification: https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html
- ACVP ML-DSA JSON Specification: https://pages.nist.gov/ACVP/draft-celi-acvp-ml-dsa.html
- ACVP documentation landing page: https://pages.nist.gov/ACVP/
- FIPS 204: https://csrc.nist.gov/pubs/fips/204/final

Every response still includes:

```json
{
  "productionReady": false,
  "profile": "local-fips204-skeleton",
  "demoOnly": true,
  "notProductionAcvp": true
}
```

## Supported Container

The skeleton accepts a registration container with an `algorithms` array:

```json
{
  "algorithms": [
    {
      "algorithm": "ML-DSA",
      "mode": "keyGen",
      "revision": "FIPS204",
      "parameterSets": ["ML-DSA-44", "ML-DSA-65"]
    }
  ],
  "label": "phase 3-3 registration session"
}
```

Each algorithm object is validated with the existing ML-DSA registration schema before negotiation.

Supported values:

- modes: `keyGen`, `sigGen`, `sigVer`
- parameter sets: `ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87`
- signature interfaces: `internal`, `external`
- signature features: `deterministic`, `externalMu`, `preHash`, `messageLength`, `contextLength`, `hashAlgs`

The current schema treats length domains as bit domains. `messageLength` must stay within the existing ML-DSA schema range and 8-bit increment rules; `contextLength` must stay within the existing 0..2040 bit range with 8-bit increment alignment.

## Negotiated Plan

`POST /acvp/v1/testSessions` now supports two local skeleton request forms:

- prompt-based Phase 3-2 sessions with `prompt`
- registration/capabilities Phase 3-3 sessions with `algorithms`

With `autoGenerateVectorSets=false`, the server creates a PostgreSQL-backed capabilities-only session with:

```json
{
  "status": "capabilitiesAccepted",
  "vectorSetIds": [],
  "vectorSetUrls": [],
  "negotiatedCapabilities": {
    "algorithm": "ML-DSA",
    "revision": "FIPS204",
    "negotiated": [],
    "unsupported": [],
    "warnings": []
  },
  "nextAction": "Server-side vector generation from negotiated capabilities is available in Phase 3-5; enable autoGenerateVectorSets or call /vectorSets/generate."
}
```

By default in Phase 3-5, registration sessions use `autoGenerateVectorSets=true`, record `stateHistory`, and become `vectorReady`. Capabilities-only sessions still return an empty vector set list until the explicit generation endpoint is called.

## SHAKE Handling

Phase 5-2 supports `SHAKE-128` and `SHAKE-256` in `hashAlgs` for external `preHash`. Capability negotiation includes SHAKE values in negotiated `hashAlgs`, vector generation creates SHAKE preHash groups, and expectedResults uses the Python oracle with the same mapping as the native wrapper:

- `SHAKE-128`: 32-byte prehash.
- `SHAKE-256`: 64-byte prehash.

Registrations that include only SHAKE preHash algorithms are accepted when the remaining ML-DSA capabilities are supported.

## Exclusions

This local skeleton intentionally does not include:

- formal random vector generation
- production database deployment
- JWT/login/mTLS
- vendor/module/OE/dependency resources
- production ACVP certification workflow

Next protocol-hardening phase: Phase 4-3 paging/query/error behavior.
