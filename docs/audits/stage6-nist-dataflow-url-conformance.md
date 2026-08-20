# Stage 6 NIST ACVP Data-flow and URL Conformance Audit

> Historical Stage 6 audit. Findings and repository paths are point-in-time
> evidence, not the current conformance status. See the
> [documentation index](../README.md).

## 1. Executive Summary

| Question | Result |
|---|---|
| Is the current data flow fully NIST conformant? | **PARTIAL** |
| Are the current URLs fully NIST conformant? | **PARTIAL** |

The Stage 6 runtime proves that ML-KEM registration, generation, download, response submission, NIST GenVal validation, and disposition aggregation work end to end. That result is not evidence of complete ACVP protocol conformance. The nested vector-set download, expected-results, result submission/update, result retrieval, and cancellation route patterns mostly match the official core protocol, and ML-KEM prompt/response content is checked against the ML-KEM algorithm specification. However, a standard enveloped test-session registration is rejected, the public vector resource uses a UUID that differs from the numeric `vsId`, and the standard `PUT /testSessions/{id}` certification flow is replaced by `POST /testSessions/{id}/submit`. Session resource payloads, algorithm discovery, paging, and `showExpected` also have material differences.

No Critical finding was identified. There are three High, four Medium, one Low, and one Informational findings. These findings do not invalidate the Stage 6 GenVal E2E evidence; they identify protocol interoperability work for a later stage.

## 2. Audit Scope

### Freeze and references

| Item | Value |
|---|---|
| Audited feature branch | `feature/stage6-mlkem-api-e2e` |
| Audited feature SHA | `b99142ddc29ddeaaafc6c3ddf14427decf6ca5b3` |
| Phase A freeze SHA | `b99142ddc29ddeaaafc6c3ddf14427decf6ca5b3` |
| Base `strict` SHA | `0f9550a185870679d511ec1ca7f62df2464325b1` |
| Audit date | 2026-07-16 |
| Official ML-KEM draft | [draft-celi-acvp-ml-kem-01, published 2026-04-16](https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html#name) |
| Official core protocol | [draft-ietf-acvp-spec-01, published 2026-04-16](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html) |
| Official NIST repository | [usnistgov/ACVP](https://github.com/usnistgov/ACVP) |
| NIST repository commit inspected | [`178fe4085b0bffc4f8b94433c965229623dc3bc7`](https://github.com/usnistgov/ACVP/tree/178fe4085b0bffc4f8b94433c965229623dc3bc7), committed 2026-04-16 |

The rendered ML-KEM draft is authoritative here for algorithm-specific registration, prompt, and response JSON. The rendered core protocol and its pinned repository sources are authoritative here for REST resources, envelopes, test-session lifecycle, paging, results, and security boundaries. Relevant pinned sources are the [URI resources](https://github.com/usnistgov/ACVP/blob/178fe4085b0bffc4f8b94433c965229623dc3bc7/src/protocol/sections/05-acvprotocol.adoc), [messaging/workflow](https://github.com/usnistgov/ACVP/blob/178fe4085b0bffc4f8b94433c965229623dc3bc7/src/protocol/sections/11-messaging.adoc), [security](https://github.com/usnistgov/ACVP/blob/178fe4085b0bffc4f8b94433c965229623dc3bc7/src/protocol/sections/06-security.adoc), and [ML-KEM source](https://github.com/usnistgov/ACVP/blob/178fe4085b0bffc4f8b94433c965229623dc3bc7/src/draft-celi-acvp-ml-kem.adoc).

### Inspected implementation surface

- FastAPI route table and generated OpenAPI schema at the freeze SHA.
- `backend/app/acvp_protocol/routes.py`, route parsers, envelope helpers, paging, errors, service URL builders, disposition, and state machine.
- Test-session and vector-set storage-facing summaries and the NIST GenVal provider boundary.
- ML-KEM registry descriptor, registration mapper, prompt/response schemas, and validation normalizer.
- Root README workflow claims and Stage 6 runtime evidence.

### Excluded areas

- NIST server deployment policy, certificate issuance, CAVP business approval, metadata resources (`vendors`, `modules`, `oes`, and validations), and production hosting topology.
- Cryptographic correctness beyond the Stage 6 live GenVal evidence.
- ML-DSA algorithm-specific schema conformance except where it shares the public ACVP flow.
- Frontend behavior, real IUT behavior, performance, denial-of-service analysis, and database durability.

## 3. Current Route Inventory

The runtime exposes 16 `/acvp/v1` routes. Unless noted, normal JSON responses use `application/json` and `[ {"acvVersion":"1.0"}, body ]`; errors use the same envelope with HTTP status plus `error.code`, `message`, `path`, `requestId`, and `X-Request-ID`.

| Method | Current URL | Purpose | NIST equivalent | Classification |
|---|---|---|---|---|
| GET | `/acvp/v1/version` | Server/version metadata | No core `/version` resource | `COMPATIBLE_EXTENSION` |
| GET | `/acvp/v1/algorithms` | Algorithm descriptors | `GET /algorithms` | `NON_CONFORMANT` payload |
| GET | `/acvp/v1/testSessions` | Filtered/paged session list | Optional `GET /testSessions` | `NON_CONFORMANT` paging/payload |
| POST | `/acvp/v1/testSessions` | Registration and optional synchronous generation | `POST /testSessions` | `NON_CONFORMANT` request/response |
| GET | `/acvp/v1/testSessions/{sessionId}` | Session summary and vector summaries | Optional `GET /testSessions/{id}` | `NON_CONFORMANT` payload |
| DELETE | `/acvp/v1/testSessions/{sessionId}` | Cancel session and child vectors | `DELETE /testSessions/{id}` | `CONFORMANT` method/path; response unspecified |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets` | Paged URLs and vector summaries | `GET /testSessions/{id}/vectorSets` | `NON_CONFORMANT` identity/paging |
| POST | `/acvp/v1/testSessions/{sessionId}/vectorSets/generate` | Explicit synchronous GenVal generation | No equivalent | `COMPATIBLE_EXTENSION` |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}` | Download prompt | Same route pattern | `NON_CONFORMANT` resource identity |
| DELETE | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}` | Cancel vector set | Same route pattern | `NON_CONFORMANT` resource identity |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/expected` | Sample expected response | Optional same route | `NON_CONFORMANT` resource identity; policy otherwise conformant |
| POST | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results` | Initial response and synchronous validation | Same route | `NON_CONFORMANT` identity/`showExpected`; body/status otherwise conformant |
| PUT | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results` | Replace/update response | Same route | `NON_CONFORMANT` identity/`showExpected`; body/status otherwise conformant |
| GET | `/acvp/v1/testSessions/{sessionId}/vectorSets/{vectorSetId}/results` | Vector disposition and case results | Same route | `NON_CONFORMANT` identity/`showExpected` |
| GET | `/acvp/v1/testSessions/{sessionId}/results` | Aggregate session disposition | Same route | `NON_CONFORMANT` returned vector URL identity |
| POST | `/acvp/v1/testSessions/{sessionId}/submit` | Locally finalize aggregate state | Standard is `PUT /testSessions/{id}` | `NON_CONFORMANT` |

### Runtime contract detail

| Route group | Request body/query | Response body | Success | Principal errors | State effect |
|---|---|---|---|---|---|
| version/algorithms | None | Local metadata or rich descriptors | 200 | 400 global unsupported query; 500 | None |
| session list | `status`, `limit`, `offset` | Official paging keys plus local duplicates/summaries | 200 | 400 invalid query/status | None |
| session create | Bare object with `algorithms` and local controls; envelope rejected | Local session/negotiation/generation summary | 200 | 400 schema; 500 GenVal/config/artifact/execution | `created -> capabilitiesAccepted -> vectorReady` when auto generation succeeds |
| session get/delete | Path ID | Local summary; cancellation summary | 200 | 404 unknown; 409 expired/legacy/state | GET may expire; DELETE sets session and active vectors `cancelled` |
| vector list | `status`, `limit`, `offset` | URLs, local summaries, paging | 200 | 400 query/status; 404 | None beyond expiry evaluation |
| explicit generate | Optional bare local generation object | Same local registration response | 200 | 400, 404, 409; 500 GenVal | `capabilitiesAccepted -> vectorReady`; atomic pre-storage preparation |
| prompt download | Path IDs | Algorithm prompt in clean ACVP envelope | 200 | 404; 409 unavailable/not ready | `ready -> downloaded`; parent aggregate may become downloaded |
| expected | Path IDs | Expected response in clean ACVP envelope | 200 | 403 non-sample; 404; 409 not ready | None |
| result POST/PUT | Direct response, ACVP envelope, or local `response` wrapper | No content | 204 runtime, OpenAPI says 200 | 400 schema; 403 expected policy; 404; 409 state; 500 GenVal | synchronous `resultsSubmitted -> validating -> validated/failed`; parent aggregate updated |
| vector results | Optional `showExpected` query | `results` disposition and case detail | 200 | 403, 404, 409 | None |
| session results | Path ID | `passed` plus vector URL/status/disposition | 200 | 404; 409 no vectors/unavailable | None |
| local submit | No body | Local final summary/history | 200 | 404; 409 incomplete/unavailable | parent `validating -> validated/failed`; freezes later vector updates |

## 4. Current Data-flow Diagram

```mermaid
flowchart TD
    C[Client] -->|public: POST /acvp/v1/testSessions, bare object| R[FastAPI route]
    R -->|server-internal| P[Pydantic request parser/model]
    P -->|server-internal| AR[Algorithm registry]
    AR -->|server-internal| M[MlkemAlgorithmModule]
    M -->|server-internal| RM[NIST registration mapper]
    RM -->|NIST GenVal process boundary| CH[GenVal Check]
    CH -->|NIST GenVal process boundary| GE[GenVal Generate]
    GE --> A[prompt + internalProjection + expectedResults]
    A -->|storage boundary| S[(SQLite/artifact storage)]
    S -->|public: clean prompt only| U[Nested vector-set URL]
    S -->|public, sample only; test-only known-good source in Stage 6| E[/expected]
    U --> C
    C -->|public: POST or PUT response| RR[Results route/parser]
    RR -->|server-internal| RS[ML-KEM response schema]
    RS -->|NIST GenVal process boundary| GV[GenVal Validate]
    GV -->|server-internal| VN[Validation normalizer]
    VN -->|storage boundary| S
    VN --> VD[Vector disposition]
    VD --> SA[Session aggregate]
    SA -->|public: GET results| C
    SA -->|local extension: POST /submit| LF[Local finalization]
```

Boundary observations:

- `internalProjection`, artifact paths, and raw process details stay server-internal in the inspected public prompt/error paths.
- `expectedResults` is stored internally and exposed only through the standard optional sample endpoint. Stage 6 tests use that endpoint only as a test-only known-good response source, not as a production oracle or IUT.
- The public URL is dereferenceable, but its `{vectorSetId}` is a storage UUID while the prompt's `vsId` is numeric. This creates two public identities for one vector set.
- Validation is synchronous. The official protocol permits a vector download retry response when generation is not ready, but does not require every implementation to generate asynchronously; synchronous validation alone is therefore not classified as a conflict.
- The local explicit-generation and local submit paths duplicate controls that are not in the standard resource table. Explicit generation is opt-in and compatible; local submit replaces a required standard lifecycle operation and is not compatible.

## 5. NIST Expected Flow

Based only on the official core protocol and ML-KEM sub-specification:

1. The client authenticates using a deployment-selected scheme when applicable. HTTPS/TLS 1.2 or greater and authentication are recommended; the exact scheme is not prescribed.
2. The client may discover algorithms with `GET /acvp/v1/algorithms`; entries contain `id`, `name`, `mode`, and `revision`. `GET /algorithms/{algorithmId}` is optional.
3. The client sends an ACVP envelope to `POST /acvp/v1/testSessions`. Its body contains `algorithms`, optional `isSample`, and optional `encryptAtRest`. Each ML-KEM registration advertises `ML-KEM`, mode, `FIPS203`, parameter sets, and mode-appropriate functions.
4. The server returns a session resource including its canonical `url`, protocol/timestamps, sample/encryption flags, publishable/passed state, vector-set URLs, and session access token.
5. The client downloads each nested numeric `vsId` vector resource. A server still generating a vector may return `vsId` plus `retry` seconds.
6. The client initially POSTs the algorithm response to the nested `/results` resource and receives no content; a full corrected resubmission uses PUT. Optional `showExpected: true` requests expected/provided detail for failed cases.
7. The client GETs vector results and session results. A sample session may GET the nested `/expected` resource.
8. Only when `publishable` and `passed` are true, the client certifies with `PUT /testSessions/{id}` and module/OE metadata. The server returns a request resource, which the client polls at `/requests/{id}` for approval/validation identity.
9. DELETE on a test session or nested vector set cancels that resource.

The core protocol defines the envelope and REST lifecycle. The ML-KEM draft defines algorithm-specific JSON and explicitly identifies `vsId` as a unique integer. The ML-KEM response example places `acvVersion` in a single response object, whereas the core protocol shows the normal two-object envelope; this discrepancy is recorded under Unknowns, and the current result parser accepts both forms.

## 6. URL Conformance Matrix

| Official resource/operation | Current operation | Result | Notes |
|---|---|---|---|
| API context `/acvp/v1` | `/acvp/v1` | `CONFORMANT` | Correct versioned base path. |
| No `/version` resource | `GET /version` | `COMPATIBLE_EXTENSION` | Does not replace a standard operation. |
| `GET /algorithms` | Same | `NON_CONFORMANT` | URL matches; descriptor contract does not. |
| Optional `GET /algorithms/{algorithmId}` | Missing | `CONFORMANT` | Operation is explicitly optional. |
| Optional `GET /testSessions` | Same | `NON_CONFORMANT` | URL matches; paging/session objects do not. |
| `POST /testSessions` | Same | `NON_CONFORMANT` | URL matches; envelope and resource contract do not. |
| Optional `GET /testSessions/{id}` | Same pattern | `NON_CONFORMANT` | Local payload differs. |
| `PUT /testSessions/{id}` | Missing | `NON_CONFORMANT` | Required certification operation is absent. |
| `DELETE /testSessions/{id}` | Same pattern | `CONFORMANT` | Cancellation semantics match at the audited level. |
| `GET /testSessions/{id}/results` | Same pattern | `NON_CONFORMANT` | Returned vector URLs use divergent UUID identity. |
| `GET /testSessions/{id}/vectorSets` | Same pattern | `NON_CONFORMANT` | URL matches; list identity and paging differ. |
| No `/vectorSets/generate` | Local POST | `COMPATIBLE_EXTENSION` | Opt-in control; standard auto path remains the default. |
| Nested vector GET/DELETE | Same patterns | `NON_CONFORMANT` | UUID path key does not equal numeric `vsId`. |
| Nested result GET/POST/PUT | Same patterns | `NON_CONFORMANT` | Route methods match; identity and `showExpected` do not. |
| Optional nested `/expected` GET | Same pattern | `NON_CONFORMANT` | Sample policy matches; identity does not. |
| No nested `/submit` | Local POST | `NON_CONFORMANT` | Replaces standard session PUT certification. |
| `/requests/{requestId}` after certification | Missing | `NON_CONFORMANT` | No asynchronous certification request resource. |

## 7. Payload / Envelope Matrix

| Area | Official | Current | Classification |
|---|---|---|---|
| Message envelope | Two-object ACVP envelope carrying negotiated `acvVersion` | Responses/errors are enveloped; result submission accepts envelope; session creation rejects it | `NON_CONFORMANT` |
| Version representation | `major.minor` in every message | Fixed `1.0`; unsupported result envelope versions return 400 | `CONFORMANT` for responses/results; create parsing is nonconformant |
| Content type | JSON, `application/json` | FastAPI JSON responses and request parsing | `CONFORMANT` |
| Registration body | `algorithms`, optional `isSample`, `encryptAtRest` | `algorithms`, `isSample`, plus local fields; no `encryptAtRest`; extra fields forbidden | `NON_CONFORMANT` |
| ML-KEM capability | Algorithm/mode/revision, prerequisite values, parameter sets, functions for encapDecap | Algorithm module validates the ML-KEM identities, parameter sets, and functions | `CONFORMANT` for audited Stage 6 scenarios |
| Create response | Canonical `url`, `acvpVersion`, timestamps, encryption/sample flags, vector URLs, `publishable`, `passed`, `accessToken` | UUID `testSessionId`, local state/negotiation/generation fields; several standard fields absent | `NON_CONFORMANT` |
| Session ID | Resource identifier; official examples are numeric but no explicit type found | UUID string | `UNCLEAR_FROM_OFFICIAL_REFERENCES` |
| Vector ID and URL | `vsId` is a unique integer and identifies nested resource | Prompt has numeric `vsId`; URL uses separate UUID `vectorSetId` | `NON_CONFORMANT` |
| Vector prompt | ACVP envelope with algorithm payload | Clean ACVP envelope; server metadata not injected into cryptographic body | `CONFORMANT` |
| Result request | Algorithm response; core envelope example; optional `showExpected` | Envelope/direct body/local wrapper accepted; valid response schema enforced | `COMPATIBLE_EXTENSION` for accepted forms; `showExpected` behavior nonconformant |
| Result submission status | No-content response; standard HTTP status indicates transport success | Runtime 204 with empty body | `CONFORMANT` |
| Result OpenAPI | Should describe runtime contract | Declares 200 and generic 422 rather than runtime 204/custom 400 | `NON_CONFORMANT` documentation |
| Vector results | `results` with numeric `vsId`, disposition, case results, optional expected/provided | Preserves normalized disposition/case detail; expected/provided always suppressed | `NON_CONFORMANT` when `showExpected` requested |
| Session results | `passed`, vector `status`, canonical `vectorSetUrl` | Same core values plus local `disposition`; URLs use UUID | `NON_CONFORMANT` identity; extra field compatible |
| Paging | `totalCount`, `incomplete`, `links.first/next/prev/last`, `data` | Core keys plus local duplicates, but uses `previous` instead of `prev` | `NON_CONFORMANT` |
| Location header | No explicit requirement found in inspected core sections | Not returned | `UNCLEAR_FROM_OFFICIAL_REFERENCES` |
| Errors | HTTP status; JSON detail permitted | Stable enveloped structured errors and request ID | `CONFORMANT` at specified level |
| Authentication | HTTPS/auth recommended; scheme not prescribed; session response describes access token | No ACVP authentication/session ownership boundary | `UNCLEAR_FROM_OFFICIAL_REFERENCES` for this internal demo deployment |

## 8. Lifecycle Matrix

| Phase | Official lifecycle | Current lifecycle | Classification |
|---|---|---|---|
| Registration | Enveloped POST creates standard session resource | Bare-object POST; capabilities checked | `NON_CONFORMANT` envelope/resource contract |
| Generation | Server supplies vector URLs; vector GET may return retry while pending | Default POST synchronously runs Check/Generate; optional explicit local generation | `COMPATIBLE_EXTENSION` timing/control, provided default standard path remains |
| Download | GET nested vector identified by numeric `vsId` | GET nested UUID URL returns prompt with a different numeric `vsId` | `NON_CONFORMANT` |
| Submission | Initial POST, corrected full response PUT, no content | POST/PUT and 204; validation happens synchronously | `CONFORMANT` methods/status; sync timing allowed |
| Validation | Server validates and reports status asynchronously or when queried | NIST GenVal Validate runs inline; state records submitted/validating/final | `COMPATIBLE_EXTENSION` timing |
| Results | GET vector and session result resources | Both resources exist and preserve NIST case detail | `CONFORMANT` structure except identity/`showExpected` defects |
| Sample expected | Optional GET only when session `isSample` is true | 200 sample, 403 non-sample | `CONFORMANT` policy |
| Resubmission | PUT full vector response before expiry | PUT accepted after pass/fail until local session submit | `CONFORMANT` broadly |
| Finalization | Passed and publishable session is certified by PUT with module/OE data; request resource returned | POST `/submit`, no body, finalizes passed or failed local aggregate, no request resource | `NON_CONFORMANT` |
| Cancellation | DELETE session/vector | DELETE session/vector and local state transition | `CONFORMANT` at specified level |

## 9. Findings

### F-01: Standard certification lifecycle is replaced

- **Finding ID:** F-01.
- **Title:** Standard certification lifecycle is replaced.
- **Current behaviour:** `POST /testSessions/{sessionId}/submit` takes no certification metadata, finalizes either a passed or failed aggregate locally, and returns a synchronous summary. There is no `PUT /testSessions/{id}` or request resource.
- **Current source file and line/function:** `backend/app/acvp_protocol/routes.py:205` (`submit_acvp_v1_test_session`); `backend/app/acvp_protocol/service.py:1288` (`submit_test_session_for_validation`).
- **Current URL/dataflow:** Client -> local POST `/submit` -> local aggregate transition -> `validated` or `failed`.
- **Official reference:** Core [message flow and test-session certification](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html), pinned [messaging source](https://github.com/usnistgov/ACVP/blob/178fe4085b0bffc4f8b94433c965229623dc3bc7/src/protocol/sections/11-messaging.adoc).
- **Expected behaviour:** A session with both `publishable` and `passed` true is certified by `PUT /testSessions/{id}` with module/OE and prerequisite metadata; the response is a request resource that can be polled.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** High.
- **Interoperability impact:** A standard client cannot certify or poll a completed validation and will not recognize the local submit operation.
- **Security/privacy impact:** Certification identity/ownership metadata and an authorization-scoped request boundary are absent; deployment impact depends on the eventual authentication model.
- **Suggested next-stage change:** Add the standard PUT certification contract and request lifecycle, keep any local finalization command clearly isolated, and enforce passed/publishable preconditions.
- **Affected tests:** Add certification method/body, failed-session rejection, request polling, idempotency, and local-extension compatibility tests; update current `/submit` tests only in that later stage.
- **Migration/compatibility concern:** Existing clients may depend on `/submit` and synchronous state. Deprecation or an explicitly local compatibility path is preferable to silent removal.

### F-02: Standard enveloped test-session registration is rejected

- **Finding ID:** F-02.
- **Title:** Standard enveloped test-session registration is rejected.
- **Current behaviour:** The create parser requires a JSON object. A standard two-object ACVP envelope is rejected before registration, although all successful responses are enveloped.
- **Current source file and line/function:** `backend/app/acvp_protocol/routes.py:70` and `:327` (`create_acvp_v1_test_session`, `_parse_session_create_request`).
- **Current URL/dataflow:** Client -> POST `/testSessions` with official envelope -> HTTP 400 `INVALID_REQUEST`.
- **Official reference:** Core [versioning/envelope and create-session examples](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html); ML-KEM [capabilities registration](https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html#capabilities-registration).
- **Expected behaviour:** Parse and validate the version object and registration body from the ACVP envelope, negotiate the version, and reject only unsupported/malformed envelopes.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** High.
- **Interoperability impact:** A protocol-conforming ACVP client cannot create any test session without a repository-specific request transformation.
- **Security/privacy impact:** No direct data leak; inconsistent parsing increases validation ambiguity at the public boundary.
- **Suggested next-stage change:** Introduce one shared envelope parser for session creation and result submission while retaining a separately documented legacy bare-body compatibility mode if needed.
- **Affected tests:** Add official create-envelope acceptance, malformed/unsupported version rejection, and bare-body compatibility tests.
- **Migration/compatibility concern:** Existing Stage 6 clients send a bare object. Preserve that form temporarily or version the breaking change.

### F-03: Public vector URL identity differs from numeric `vsId`

- **Finding ID:** F-03.
- **Title:** Public vector URL identity differs from numeric `vsId`.
- **Current behaviour:** GenVal supplies a numeric `vsId` in the prompt, but storage generates an independent UUID `vectorSetId` and uses that UUID in every returned/dereferenceable vector URL.
- **Current source file and line/function:** `backend/app/acvp_protocol/service.py:678` (`_prepare_nist_generated_vector_sets`), `:1555` (`_vector_set_summary`), and `:1585` (`_nested_vector_set_path`).
- **Current URL/dataflow:** `/testSessions/{uuid}/vectorSets/{uuid}` returns a prompt whose body contains a different numeric `vsId`.
- **Official reference:** ML-KEM [top-level vector schema](https://pages.nist.gov/ACVP/draft-celi-acvp-ml-kem.html#test-vectors) defines `vsId` as a unique integer; core vector resources associate the nested vector resource with that `vsId`.
- **Expected behaviour:** One stable public vector identity should connect `vectorSetUrls`, the nested path, request/response `vsId`, and results.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** High.
- **Interoperability impact:** Standard clients keying requests and responses by `vsId` cannot derive or correlate the resource URL without local summary fields.
- **Security/privacy impact:** No direct secret exposure; duplicate identifiers increase the risk of cross-resource association mistakes.
- **Suggested next-stage change:** Define a canonical public numeric `vsId` mapping and keep the UUID server-internal, with an explicit migration strategy for persisted URLs.
- **Affected tests:** Update route correlation, list/download/result/session aggregate, unknown-ID, and persistence/restart tests.
- **Migration/compatibility concern:** Existing URLs, evidence, and stored records use UUIDs; aliases or data migration may be required.

### F-04: Test-session request and resource payloads omit standard properties

- **Finding ID:** F-04.
- **Title:** Test-session request and resource payloads omit standard properties.
- **Current behaviour:** `encryptAtRest` is not accepted; create/get responses omit canonical `url`, `acvpVersion`, `encryptAtRest`, `publishable`, `passed`, and `accessToken`, and instead expose local negotiation/state/generation fields.
- **Current source file and line/function:** `backend/app/models.py:11` (`AcvpV1TestSessionCreateRequest`); `backend/app/acvp_protocol/service.py:523` (`_registration_session_response`) and `:1510` (`_session_summary`).
- **Current URL/dataflow:** POST/GET session resources return a local workflow representation rather than the core test-session resource.
- **Official reference:** Core [Test Sessions and Create a New Test Session](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html).
- **Expected behaviour:** Accept the standard optional request fields and return the defined session resource properties; extensions may be additional namespaced or clearly local data.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** Medium.
- **Interoperability impact:** Generic clients cannot locate or interpret the session using the standard resource contract and an official `encryptAtRest` request is rejected.
- **Security/privacy impact:** Missing `encryptAtRest` and access-token semantics matter in deployments requiring protected storage/authorization; this audit does not assert that those deployment features are mandatory here.
- **Suggested next-stage change:** Add the standard fields and semantics first, then isolate local workflow metadata without removing it abruptly.
- **Affected tests:** Session create/get/list payload, encryption flag, canonical URL, pass/publishable state, and auth-boundary tests.
- **Migration/compatibility concern:** Preserve local keys during a transition because the frontend/tests may consume them.

### F-05: Algorithm discovery descriptor shape is not the core shape

- **Finding ID:** F-05.
- **Title:** Algorithm discovery descriptor shape is not the core shape.
- **Current behaviour:** Each descriptor uses `providerId`, `algorithm`, `displayName`, `modes`, schema versions, execution metadata, and capabilities. It has no numeric `id` or `name`, and no detail route.
- **Current source file and line/function:** `backend/app/acvp_core/algorithm_descriptor.py:53` (`to_dict`); `backend/app/acvp_protocol/service.py:106` (`algorithms`).
- **Current URL/dataflow:** GET `/algorithms` returns implementation registry descriptors rather than core discovery records.
- **Official reference:** Core [Algorithms Listing](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html) specifies `id`, `name`, `mode`, and `revision` entries; detail GET is optional.
- **Expected behaviour:** Return standard listing fields for each supported algorithm/mode/revision; richer registry metadata may be an extension.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** Medium.
- **Interoperability impact:** A generic client cannot enumerate algorithm IDs/names using the official shape.
- **Security/privacy impact:** Low; current descriptors disclose implementation/provider details but no secrets.
- **Suggested next-stage change:** Add a standard projection per identity and move rich descriptors under an explicit extension or separate local endpoint.
- **Affected tests:** Discovery shape, one-entry-per-mode behavior, optional detail endpoint decision, and local metadata compatibility.
- **Migration/compatibility concern:** Current consumers may expect one rich descriptor containing multiple modes.

### F-06: Paging link key and resource entries differ from the required format

- **Finding ID:** F-06.
- **Title:** Paging link key and resource entries differ from the required format.
- **Current behaviour:** Paged bodies include required top-level keys but use `links.previous` instead of `links.prev`, and add duplicate collection, `pagination`, query, and summary fields.
- **Current source file and line/function:** `backend/app/acvp_protocol/paging.py:63` (`build_paged_body`) and `:142` (`_paging_links`); service list functions at `backend/app/acvp_protocol/service.py:350` and `:903`.
- **Current URL/dataflow:** Session and vector-set listing responses cannot be navigated by a client looking for `links.prev`.
- **Official reference:** Core [Paging](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html) requires `totalCount`, `incomplete`, `links.first/next/prev/last`, and `data`.
- **Expected behaviour:** Emit `prev`; additional fields must not replace required fields. Vector list `data` should retain the operation's defined resource representation.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** Medium.
- **Interoperability impact:** Backward navigation breaks for strict clients; duplicate representations create parsing ambiguity.
- **Security/privacy impact:** None identified.
- **Suggested next-stage change:** Add `prev` as canonical, decide a compatibility period for `previous`, and separate local summaries from the standard collection projection.
- **Affected tests:** First/middle/last/empty page links and standard list-body shape.
- **Migration/compatibility concern:** Consumers may rely on `previous`, `pagination`, `testSessions`, `vectorSetUrls`, or `vectorSets`.

### F-07: `showExpected` is accepted but discarded

- **Finding ID:** F-07.
- **Title:** `showExpected` is accepted but discarded.
- **Current behaviour:** A true value is denied for non-sample sessions, but for sample sessions it is removed before validation and persisted as false. Result construction always receives `show_expected=False`; GET query `showExpected=true` is also ignored for sample results.
- **Current source file and line/function:** `backend/app/acvp_protocol/routes.py:146` and `:189`; `backend/app/acvp_protocol/service.py:1042`, especially `:1159`, `:1184`, and `:1224`.
- **Current URL/dataflow:** Client submits `showExpected: true` -> successful validation -> failing result omits official expected/provided diagnostic data.
- **Official reference:** Core [Submit Results and Request Validation Results](https://pages.nist.gov/ACVP/draft-fussell-acvp-spec.html) states that true requests additional expected/provided information for failing cases.
- **Expected behaviour:** If the server accepts true, preserve the request and include available expected/provided detail for failed cases; continue denying non-sample disclosure under local policy.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** Medium.
- **Interoperability impact:** Clients receive less diagnostic information than explicitly requested, with no error signaling that the option was ignored.
- **Security/privacy impact:** Current suppression prevents disclosure; a later fix must preserve the sample/non-sample boundary.
- **Suggested next-stage change:** Persist the accepted flag per submission and pass it to result construction only for authorized sample sessions.
- **Affected tests:** Sample failed result with true/false, PUT replacement, GET result behavior, and all non-sample denial/leakage tests.
- **Migration/compatibility concern:** Exposing expected values changes response size and sensitivity; default must remain false.

### F-08: OpenAPI success/error declarations disagree with runtime

- **Finding ID:** F-08.
- **Title:** OpenAPI success/error declarations disagree with runtime.
- **Current behaviour:** FastAPI declares 200 for POST/PUT result routes although runtime returns 204, and generated schemas retain generic validation responses rather than documenting custom enveloped 400 errors.
- **Current source file and line/function:** `backend/app/acvp_protocol/routes.py:146` and `:167`; `backend/app/acvp_protocol/service.py:1189`.
- **Current URL/dataflow:** Generated clients may expect a JSON 200 response where the server correctly emits empty 204.
- **Official reference:** Core result submission requires a no-content response and standard HTTP status signaling.
- **Expected behaviour:** OpenAPI must describe the actual 204 and public error envelope/statuses.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** Low.
- **Interoperability impact:** Generated SDKs and API validators may mishandle otherwise valid submissions.
- **Security/privacy impact:** None identified.
- **Suggested next-stage change:** Declare route status/response models and shared error responses without changing runtime semantics.
- **Affected tests:** OpenAPI snapshot/contract tests and generated-client smoke test.
- **Migration/compatibility concern:** Documentation correction can reveal assumptions in generated clients but should not require runtime compatibility logic.

### F-09: Public workflow documentation is incomplete and partly stale

- **Finding ID:** F-09.
- **Title:** Public workflow documentation is incomplete and partly stale.
- **Current behaviour:** The root README describes strict GenVal operation but does not inventory all current list/delete/PUT/expected/submit routes, and the GenVal integration document remains ML-DSA-focused despite ML-KEM support.
- **Current source file and line/function:** `README.md` workflow/API sections; `docs/nist-genval-integration.md`.
- **Current URL/dataflow:** Users cannot distinguish standard routes, compatible extensions, and the nonstandard final submit flow from documentation alone.
- **Official reference:** Official core URI resource table and message flow linked above.
- **Expected behaviour:** Documentation should label each public operation by standard/extension status and show the actual lifecycle.
- **Classification:** `NON_CONFORMANT`.
- **Severity:** Informational.
- **Interoperability impact:** Increases integration mistakes and hides required migration work.
- **Security/privacy impact:** None identified.
- **Suggested next-stage change:** Update documentation only after the next protocol modification stage fixes or explicitly versions the contracts.
- **Affected tests:** Documentation/link checks if introduced.
- **Migration/compatibility concern:** Avoid documenting the current local submit flow as NIST-standard during transition.

## 10. Compatible Extensions

| Extension | Why compatible at the freeze SHA | Guardrail for next stage |
|---|---|---|
| `GET /acvp/v1/version` | Does not replace a standard route | Label it local and do not use it instead of per-message `acvVersion`. |
| `POST .../vectorSets/generate` | Explicit opt-in; default registration still generates vectors | Keep standard clients independent of this route. |
| `autoGenerateVectorSets`, `campaignSeed`, `testsPerGroup`, `expiresInSeconds`, `label`, `metadata` | Local registration controls are not forbidden by the inspected algorithm draft | Isolate/name them as extensions and also accept all standard fields. |
| `status` filters and richer list/session/vector summaries | Additional observability does not inherently prevent standard projection | Preserve required standard keys and move duplicated data under an extension boundary. |
| Direct result object and local `{response: ...}` wrapper | The parser also accepts the core envelope, increasing input compatibility | Keep one canonical documented form; validate version whenever supplied. |
| `X-Request-ID`, structured error code/path/details | Core permits JSON troubleshooting information | Continue redacting absolute paths, credentials, and internal artifacts. |
| `workflowPolicy`, `executionBackend`, provider/source metadata | Useful implementation provenance outside cryptographic prompt/expected bodies | Keep out of algorithm payloads and preferably group under a local extension object. |
| Synchronous GenVal generation/validation | Official references permit retry but do not mandate asynchronous vector generation or validation | Bound execution time and retain structured unavailable errors/no fallback. |
| Extra session-result `disposition` | Required `status` remains present | Do not let the extension replace official status vocabulary. |

`POST /testSessions/{id}/submit` is intentionally excluded from this table because it replaces, rather than supplements, the standard certification flow.

## 11. Unknowns

- The core protocol examples use numeric test-session IDs but the inspected text does not state an explicit test-session ID JSON type. The session UUID alone is therefore not classified as nonconformant.
- The core protocol does not explicitly require a `Location` header for session creation in the inspected sections.
- Exact success codes and response bodies for DELETE are not specified beyond standard HTTP signaling and cancellation semantics.
- The ML-KEM response section shows one object containing `acvVersion`, while the core protocol specifies the two-object envelope. Current acceptance of envelope, direct body, and wrapper avoids rejecting either official presentation, but a later canonicalization decision should document the precedence.
- HTTPS and authentication are recommended and the authentication mechanism is deployment-specific. Whether this repository will operate as a validation authority, an internal organizational server, or only a local demo is not established, so absence of mTLS/JWT/session ownership is not given a conformance severity here.
- The official references allow generation retry and request polling but do not require a specific background architecture or maximum synchronous processing duration.
- The official error section allows JSON diagnostics but does not prescribe the repository's detailed error-code vocabulary, `requestId`, or every status mapping.
- The relationship between a future NIST production ACVTS deployment and this vendored GenVal-based server is outside the audited repository boundary.

## 12. Recommended Next Modification Stage

1. **Priority 0 - Interoperability blockers:** Accept the standard create envelope, unify public vector identity with numeric `vsId`, and add standard session PUT certification plus request polling.
2. **Priority 1 - Session contract:** Add standard session request/resource fields and lifecycle semantics, including `encryptAtRest`, canonical URLs, and passed/publishable state; decide the deployment authentication boundary before implementing token behavior.
3. **Priority 2 - Discovery and collections:** Produce standard algorithm projections and correct paging (`prev`, canonical `data`) while preserving local metadata under an explicit extension.
4. **Priority 3 - Results contract:** Honor sample `showExpected`, retain non-sample confidentiality, and make OpenAPI declare 204/custom errors.
5. **Priority 4 - Extension isolation and migration:** Version or deprecate `/submit`, UUID URLs, bare registration bodies, local wrappers, and duplicate list fields with compatibility tests.
6. **Priority 5 - Documentation:** After behavior is implemented, update README/data-flow documentation and publish a standard-versus-local endpoint table.

Each priority should be delivered in a modification stage with protocol fixtures and client-level tests. No recommendation in this report was implemented during Stage 6 Phase B.

## 13. No-change Attestation

The NIST conformance audit was read-only.
No production route, data flow, schema, test, or runtime behaviour was changed
in response to audit findings during Stage 6.

Phase B changed files:

```text
docs/audits/stage6-nist-dataflow-url-conformance.md
```
