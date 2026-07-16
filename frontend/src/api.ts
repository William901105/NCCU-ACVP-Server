import { acvpEnvelope, isAcvpEnvelope, isAcvpRequestUrl, unwrapAcvpEnvelope } from "./acvp";
import type {
  AcvpCertificationRequest,
  AcvpRequestResource,
  AcvpSessionDetail,
  AcvpSessionRegistration,
  AcvpSessionSummary,
  AcvpStrictSessionResultItem,
  AcvpStrictVectorSetResults,
  AcvpVectorSetId,
  AcvpVectorSetPayload,
  AcvpVectorSetSummary,
  JsonValue,
  NormalizedExpectedView,
  NormalizedSessionResultsView,
  NormalizedVectorSetResultView,
  NormalizedVectorSetView
} from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

interface RequestOptions extends RequestInit {
  preserveAcvpEnvelope?: boolean;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly path?: string;
  readonly payload?: unknown;

  constructor(message: string, status: number, payload?: unknown, code?: string, path?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.code = code;
    this.path = path;
  }
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const payload = await requestMaybeJson<T>(path, options);
  if (payload === undefined) {
    throw new Error("Response did not include a JSON body.");
  }
  return payload;
}

export async function requestJson<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, options);
}

export async function requestMaybeJson<T>(
  path: string,
  options?: RequestOptions
): Promise<T | undefined> {
  const { preserveAcvpEnvelope = false, ...requestOptions } = options ?? {};
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(requestOptions.headers ?? {})
    },
    ...requestOptions
  });
  const payload = await parseResponsePayload(response);
  if (!response.ok) {
    throw buildApiError(response, payload);
  }
  if (payload === undefined) {
    return undefined;
  }
  return (preserveAcvpEnvelope ? payload : unwrapAcvpEnvelope(payload)) as T;
}

export async function listAcvpSessions(status?: string): Promise<AcvpSessionSummary[]> {
  const payload = await request<{ testSessions: AcvpSessionSummary[] }>(
    withQuery("/acvp/v1/testSessions", { status })
  );
  return payload.testSessions;
}

export async function createAcvpSession(
  registration: AcvpSessionRegistration
): Promise<AcvpSessionDetail> {
  return request<AcvpSessionDetail>("/acvp/v1/testSessions", {
    method: "POST",
    body: JSON.stringify(acvpEnvelope(registration))
  });
}

export async function getAcvpSession(sessionId: string): Promise<AcvpSessionDetail> {
  return request<AcvpSessionDetail>(`/acvp/v1/testSessions/${encodeURIComponent(sessionId)}`);
}

export async function getAcvpSessionVectorSets(
  sessionId: string
): Promise<AcvpVectorSetSummary[]> {
  const payload = await request<{ vectorSets: AcvpVectorSetSummary[] }>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets`
  );
  return payload.vectorSets;
}

export async function getAcvpVectorSetPrompt(
  sessionId: string,
  vsId: AcvpVectorSetId
): Promise<NormalizedVectorSetView> {
  const payload = await requestJson<unknown>(vectorPath(sessionId, vsId), {
    preserveAcvpEnvelope: true
  });
  return normalizeVectorSetPrompt(payload, sessionId, vsId);
}

export async function getAcvpExpectedResults(
  sessionId: string,
  vsId: AcvpVectorSetId
): Promise<NormalizedExpectedView> {
  const payload = await requestJson<unknown>(`${vectorPath(sessionId, vsId)}/expected`, {
    preserveAcvpEnvelope: true
  });
  return normalizeExpectedResults(payload);
}

export async function submitAcvpVectorSetResults(
  sessionId: string,
  vsId: AcvpVectorSetId,
  response: JsonValue
): Promise<NormalizedVectorSetResultView | undefined> {
  if (!isAcvpEnvelope(response) && !isRecord(response)) {
    throw new Error("IUT response JSON must be an object or canonical ACVP envelope.");
  }
  const body = isAcvpEnvelope(response) ? response : acvpEnvelope(response);
  const payload = await requestMaybeJson<unknown>(`${vectorPath(sessionId, vsId)}/results`, {
    method: "POST",
    body: JSON.stringify(body),
    preserveAcvpEnvelope: true
  });
  return payload === undefined ? undefined : normalizeVectorSetResults(payload);
}

export async function getAcvpVectorSetResults(
  sessionId: string,
  vsId: AcvpVectorSetId
): Promise<NormalizedVectorSetResultView> {
  const payload = await requestJson<unknown>(`${vectorPath(sessionId, vsId)}/results`, {
    preserveAcvpEnvelope: true
  });
  return normalizeVectorSetResults(payload);
}

export async function getAcvpSessionResults(
  sessionId: string
): Promise<NormalizedSessionResultsView> {
  const payload = await requestJson<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/results`,
    { preserveAcvpEnvelope: true }
  );
  return normalizeSessionResults(payload);
}

export async function certifyAcvpSession(
  sessionId: string,
  certification: AcvpCertificationRequest
): Promise<AcvpRequestResource> {
  const payload = await requestJson<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PUT",
      body: JSON.stringify(acvpEnvelope(certification)),
      preserveAcvpEnvelope: true
    }
  );
  return normalizeRequestResource(payload);
}

export async function getAcvpRequest(requestUrl: string): Promise<AcvpRequestResource> {
  if (!isAcvpRequestUrl(requestUrl)) {
    throw new ApiError(
      "Request resource URL must match /acvp/v1/requests/{numericId}.",
      400,
      undefined,
      "INVALID_REQUEST_URL",
      requestUrl
    );
  }
  const payload = await requestJson<unknown>(requestUrl, { preserveAcvpEnvelope: true });
  return normalizeRequestResource(payload);
}

export function expectedDeniedView(reason: string): NormalizedExpectedView {
  return { available: false, denied: true, reason };
}

async function parseResponsePayload(response: Response): Promise<unknown | undefined> {
  if (response.status === 204) {
    return undefined;
  }
  const text = await response.text();
  if (!text) {
    return undefined;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function buildApiError(response: Response, payload: unknown): ApiError {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  const detail = extractErrorDetail(body);
  return new ApiError(
    detail.message || response.statusText,
    response.status,
    payload,
    detail.code,
    detail.path
  );
}

function extractErrorDetail(payload: unknown): { message: string; code?: string; path?: string } {
  if (isRecord(payload)) {
    const error = payload.error;
    if (isRecord(error)) {
      return {
        message: stringValue(error.message) ?? stringValue(error.detail) ?? "Request failed.",
        code: stringValue(error.code),
        path: stringValue(error.path)
      };
    }
    if (typeof payload.detail === "string") {
      return { message: payload.detail };
    }
    const message = stringValue(payload.message);
    if (message) {
      return {
        message,
        code: stringValue(payload.code),
        path: stringValue(payload.path)
      };
    }
  }
  return { message: typeof payload === "string" ? payload : "Request failed." };
}

function vectorPath(sessionId: string, vsId: AcvpVectorSetId): string {
  return `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets/${vsId}`;
}

function withQuery(
  path: string,
  params: Record<string, string | number | boolean | undefined | null>
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  }
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

function normalizeVectorSetPrompt(
  payload: unknown,
  sessionId: string,
  vsId: AcvpVectorSetId
): NormalizedVectorSetView {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  if (!isVectorSetPayload(body)) {
    throw new Error("Vector set response did not contain an ACVP prompt payload.");
  }
  return {
    vectorSetId: vsId,
    sessionId,
    status: stringValue(body.status),
    prompt: body,
    raw: payload,
    sourceShape: "strict-payload"
  };
}

function normalizeExpectedResults(payload: unknown): NormalizedExpectedView {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  if (isVectorSetPayload(body)) {
    return {
      available: true,
      denied: false,
      expectedResults: body,
      raw: payload,
      sourceShape: "strict-payload"
    };
  }
  return {
    available: false,
    denied: false,
    reason: "Expected results response did not contain a vector set payload.",
    raw: payload
  };
}

function normalizeVectorSetResults(payload: unknown): NormalizedVectorSetResultView {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  const strictResults = extractStrictVectorSetResults(body);
  if (!strictResults) {
    throw new Error("Vector set results response did not contain a recognizable result body.");
  }
  return {
    disposition: strictResults.results.disposition,
    tests: strictResults.results.tests,
    raw: payload,
    acvpResults: strictResults,
    sourceShape: "strict-payload",
    status: isRecord(body) ? stringValue(body.status) : undefined
  };
}

function normalizeSessionResults(payload: unknown): NormalizedSessionResultsView {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  if (!isStrictSessionResults(body)) {
    throw new Error("Test session results response did not contain a recognizable result body.");
  }
  return {
    passed: body.passed,
    results: body.results,
    raw: payload,
    sourceShape: "strict-payload"
  };
}

function normalizeRequestResource(payload: unknown): AcvpRequestResource {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  if (!isRecord(body) || typeof body.url !== "string" || typeof body.status !== "string") {
    throw new Error("ACVP request response did not contain a request resource.");
  }
  return {
    url: body.url,
    status: body.status,
    message: stringValue(body.message),
    approvedUrl: stringValue(body.approvedUrl),
    raw: payload
  };
}

function extractStrictVectorSetResults(payload: unknown): AcvpStrictVectorSetResults | undefined {
  if (!isRecord(payload)) {
    return undefined;
  }
  if (isStrictVectorSetResults(payload)) {
    return payload;
  }
  return isStrictVectorSetResults(payload.acvpResults) ? payload.acvpResults : undefined;
}

function isVectorSetPayload(value: unknown): value is AcvpVectorSetPayload {
  return (
    isRecord(value) &&
    Array.isArray(value.testGroups) &&
    (value.vsId === undefined || typeof value.vsId === "number")
  );
}

function isStrictVectorSetResults(value: unknown): value is AcvpStrictVectorSetResults {
  return (
    isRecord(value) &&
    isRecord(value.results) &&
    typeof value.results.disposition === "string" &&
    Array.isArray(value.results.tests)
  );
}

function isStrictSessionResults(
  value: unknown
): value is { passed: boolean; results: AcvpStrictSessionResultItem[] } {
  return isRecord(value) && typeof value.passed === "boolean" && Array.isArray(value.results);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
