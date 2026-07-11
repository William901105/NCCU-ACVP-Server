# Stage 3: Algorithm-neutral ACVP Core

## Target Architecture

Stage 3 separates the strict protocol runtime from concrete algorithm code:

```text
FastAPI routes -> ACVP protocol -> core registry/interfaces -> algorithm module
                                      |
                                      +-> NIST GenVal execution adapter
```

The protocol, GenVal, and storage packages do not import ML-DSA. The sole
composition root is `acvp_core/bootstrap.py`, which currently registers one
`MldsaAlgorithmModule`.

## Core Contract

`AlgorithmIdentity` is an immutable, hashable `(algorithm, mode, revision)`
value and is the registry key. `AlgorithmDescriptor` is immutable and produces
detached, stable JSON containing provider identity, modes, parameter sets,
schema versions, execution backend, NIST references, and module-specific
capability metadata.

`AcvpAlgorithmModule` is strict-only. A module validates registrations,
prompts, and responses; negotiates capabilities; maps one registration to NIST
input; and normalizes NIST validation output. It has no local generation,
expected-result generation, result comparison, storage, HTTP, or subprocess
responsibilities.

## Registry and Dependency Injection

`AlgorithmModuleRegistry` uses `AlgorithmIdentity` keys, enforces unique stable
provider IDs and identities, validates descriptor/module agreement, and emits
descriptors in deterministic order. There is no global registry.

The FastAPI lifespan builds the production registry once and stores it at
`app.state.algorithm_registry`. Routes obtain it through a dependency and pass
it explicitly to protocol services. Tests can override that dependency with a
custom registry.

## ML-DSA Module

ML-DSA now lives under `backend/app/algorithms/mldsa/`. The module owns its
descriptor, schemas, validators, capability negotiation, NIST mapper, and
validation normalizer. Its stable provider ID is
`nist-ml-dsa-fips204`. NIST GenVal remains the only execution backend.

## Dependency Rules

- `acvp_protocol`, `genval`, `storage`, and general `acvp_core` code may depend
  only on core contracts.
- Concrete algorithm imports are permitted only in the bootstrap composition
  root.
- Algorithm modules may depend on core types and shared parsing helpers, but
  not on HTTP, storage, or GenVal subprocess execution.
- Adding a module must not require edits to protocol, GenVal, storage, or the
  existing ML-DSA module.

## Evidence

A test-only `TEST-ALGORITHM` module proves custom registration validation,
NIST mapping, validation normalization, descriptor listing, and dependency
override behavior. AST-based tests enforce concrete import boundaries and the
absence of the previous provider/global-registry architecture.

Backend verification reports `59 passed`. The frontend TypeScript/Vite build
passes with the descriptor-driven `/algorithms` response. The Stage 3 OpenAPI
snapshot is `docs/baseline/openapi-stage3-algorithm-neutral.json`; Stage 0,
Stage 1, and Stage 2 snapshots remain unchanged.

## Stage 4

Stage 4 can add a mixed-algorithm execution planner and split the remaining
protocol service responsibilities. Those changes are intentionally outside
Stage 3; no additional production algorithm has been registered here.
