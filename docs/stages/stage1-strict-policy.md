# Stage 1: Strict ACVP Policy

> Historical Stage 1 implementation record. It is not a current setup or API
> guide. See the [documentation index](../README.md).

## Scope

Stage 1 converts `/acvp/v1` to one fixed policy:

```text
workflowPolicy: strict
executionBackend: nist-genval
```

There are no runtime workflow or generation profile selectors. Query attempts
are rejected by centralized request middleware, while body attempts return
explicit policy errors.

## Contract

- Test-session creation accepts registration containers only.
- Prompt sessions and automatic local expected-result generation are disabled.
- NIST GenVal performs every `/acvp/v1` generation and validation operation.
- A GenVal failure is returned to the caller; no provider or oracle fallback is
  attempted.
- New sessions and vectors store and return the fixed policy metadata.
- Non-sample expected results remain server-side. Sample expected results are
  available through the nested expected endpoint.
- Legacy local sessions can be listed or read, but state-changing generation,
  submission, and validation operations return
  `LEGACY_LOCAL_SESSION_NOT_SUPPORTED`.

## Compatibility and Stage 2

The repository intentionally retains the local oracle, validator, import and
demo code at this stage. These components are not in the strict `/acvp/v1`
execution path. Stage 2 removes the unreachable local runtime implementation
and its remaining legacy surfaces.

The pre-refactor OpenAPI and storage snapshots remain under `docs/baseline/`.
`openapi-stage1-strict.json` is the new strict API snapshot and is generated
without changing the pre-strict baseline.
