import type {
  AcvpEnvelope,
  AcvpExpectedPayload,
  AcvpSessionDetail,
  AcvpSessionSummary,
  AcvpStrictSessionResultItem,
  AcvpStrictVectorSetResultTest,
  AcvpStrictVectorSetResults,
  AcvpVectorSetPayload,
  AcvpVectorSetSummary,
  JsonObject,
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

export interface AcvpClientOptions {
  isSample?: boolean;
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

export function isAcvpEnvelope(payload: unknown): payload is AcvpEnvelope<unknown> {
  return (
    Array.isArray(payload) &&
    payload.length >= 2 &&
    isRecord(payload[0]) &&
    typeof payload[0].acvVersion === "string"
  );
}

export function unwrapAcvpEnvelope<T>(payload: unknown): T {
  if (isAcvpEnvelope(payload)) {
    return payload[1] as T;
  }
  return payload as T;
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

export async function requestMaybeJson<T>(path: string, options?: RequestOptions): Promise<T | undefined> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    },
    ...options
  });

  const payload = await parseResponsePayload(response);

  if (!response.ok) {
    throw buildApiError(response, payload);
  }

  if (payload === undefined) {
    return undefined;
  }

  if (options?.preserveAcvpEnvelope) {
    return payload as T;
  }

  return unwrapAcvpEnvelope<T>(payload);
}

export async function requestNoContentAware<T>(path: string, options?: RequestOptions): Promise<T | undefined> {
  return requestMaybeJson<T>(path, options);
}

export async function listAcvpSessions(options: AcvpClientOptions = {}, status?: string): Promise<AcvpSessionSummary[]> {
  const payload = await request<{ testSessions: AcvpSessionSummary[] }>(
    withQuery("/acvp/v1/testSessions", { status })
  );
  return payload.testSessions;
}

export async function createAcvpSession(payload: JsonValue, options: AcvpClientOptions = {}): Promise<AcvpSessionDetail> {
  const body = mergeSessionOptions(payload, options);
  return request<AcvpSessionDetail>(
    "/acvp/v1/testSessions",
    {
      method: "POST",
      body: JSON.stringify(body)
    }
  );
}

export async function getAcvpSession(sessionId: string, options: AcvpClientOptions = {}): Promise<AcvpSessionDetail> {
  return request<AcvpSessionDetail>(`/acvp/v1/testSessions/${encodeURIComponent(sessionId)}`);
}

export async function getAcvpSessionVectorSets(
  sessionId: string,
  options: AcvpClientOptions = {}
): Promise<AcvpVectorSetSummary[]> {
  const payload = await request<{ vectorSets: AcvpVectorSetSummary[] }>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets`
  );
  return payload.vectorSets;
}

export async function getAcvpVectorSetPrompt(
  sessionId: string,
  vectorSetId: string,
  options: AcvpClientOptions = {}
): Promise<NormalizedVectorSetView> {
  const payload = await requestJson<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets/${encodeURIComponent(vectorSetId)}`
  );
  return normalizeVectorSetPrompt(payload, sessionId, vectorSetId);
}

export async function getAcvpExpectedResults(
  sessionId: string,
  vectorSetId: string,
  options: AcvpClientOptions = {}
): Promise<NormalizedExpectedView> {
  const payload = await requestJson<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets/${encodeURIComponent(vectorSetId)}/expected`
  );
  return normalizeExpectedResults(payload);
}

export async function submitAcvpVectorSetResults(
  sessionId: string,
  vectorSetId: string,
  response: JsonValue,
  options: AcvpClientOptions = {}
): Promise<NormalizedVectorSetResultView | undefined> {
  const body = isAcvpEnvelope(response) ? response : { response };
  const payload = await requestNoContentAware<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets/${encodeURIComponent(vectorSetId)}/results`,
    {
      method: "POST",
      body: JSON.stringify(body)
    }
  );

  if (payload === undefined) {
    return undefined;
  }

  return normalizeVectorSetResults(payload);
}

export async function getAcvpVectorSetResults(
  sessionId: string,
  vectorSetId: string,
  options: AcvpClientOptions = {}
): Promise<NormalizedVectorSetResultView> {
  const payload = await requestJson<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/vectorSets/${encodeURIComponent(vectorSetId)}/results`
  );
  return normalizeVectorSetResults(payload);
}

export async function getAcvpSessionResults(
  sessionId: string,
  options: AcvpClientOptions = {}
): Promise<NormalizedSessionResultsView> {
  const payload = await requestJson<unknown>(
    `/acvp/v1/testSessions/${encodeURIComponent(sessionId)}/results`
  );
  return normalizeSessionResults(payload);
}

export function expectedDeniedView(reason: string): NormalizedExpectedView {
  return {
    available: false,
    denied: true,
    reason
  };
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
  return new ApiError(detail.message || response.statusText, response.status, payload, detail.code, detail.path);
}

function extractErrorDetail(payload: unknown): { message: string; code?: string; path?: string } {
  if (isRecord(payload)) {
    const error = payload.error;
    if (isRecord(error)) {
      const message = stringValue(error.message) ?? stringValue(error.detail) ?? "Request failed.";
      return {
        message,
        code: stringValue(error.code),
        path: stringValue(error.path)
      };
    }
    const detail = payload.detail;
    if (typeof detail === "string") {
      return { message: detail };
    }
    if (detail !== undefined) {
      return { message: JSON.stringify(detail) };
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
  if (typeof payload === "string") {
    return { message: payload };
  }
  return { message: "Request failed." };
}

function withQuery(path: string, params: Record<string, string | number | boolean | undefined | null>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  }
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

function mergeSessionOptions(payload: JsonValue, options: AcvpClientOptions): JsonValue {
  if (!isRecord(payload) || Array.isArray(payload)) {
    return payload;
  }
  const body: Record<string, JsonValue> = { ...(payload as JsonObject) };
  if (options.isSample !== undefined) {
    body.isSample = options.isSample;
  }
  return body;
}

function normalizeVectorSetPrompt(payload: unknown, sessionId: string, vectorSetId: string): NormalizedVectorSetView {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  if (isVectorSetPayload(body)) {
    return {
      vectorSetId,
      sessionId,
      status: stringValue(isRecord(body) ? body.status : undefined),
      prompt: body,
      raw: payload,
      sourceShape: "strict-payload"
    };
  }
  throw new Error("Vector set response did not contain an ACVP prompt payload.");
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
  if (strictResults) {
    return {
      disposition: strictResults.results.disposition,
      tests: strictResults.results.tests,
      raw: payload,
      acvpResults: strictResults,
      sourceShape: "strict-payload",
      status: isRecord(body) ? stringValue(body.status) : undefined
    };
  }

  throw new Error("Vector set results response did not contain a recognizable result body.");
}

function normalizeSessionResults(payload: unknown): NormalizedSessionResultsView {
  const body = unwrapAcvpEnvelope<unknown>(payload);
  if (isStrictSessionResults(body)) {
    return {
      passed: body.passed,
      results: body.results,
      raw: payload,
      sourceShape: "strict-payload"
    };
  }

  throw new Error("Test session results response did not contain a recognizable result body.");
}

function extractStrictVectorSetResults(payload: unknown): AcvpStrictVectorSetResults | undefined {
  if (!isRecord(payload)) {
    return undefined;
  }
  if (isStrictVectorSetResults(payload)) {
    return payload;
  }
  if (isStrictVectorSetResults(payload.acvpResults)) {
    return payload.acvpResults;
  }
  return undefined;
}

function isVectorSetPayload(value: unknown): value is AcvpVectorSetPayload {
  return isRecord(value) && Array.isArray(value.testGroups);
}

function isStrictVectorSetResults(value: unknown): value is AcvpStrictVectorSetResults {
  return (
    isRecord(value) &&
    isRecord(value.results) &&
    typeof value.results.disposition === "string" &&
    Array.isArray(value.results.tests)
  );
}

function isStrictSessionResults(value: unknown): value is { passed: boolean; results: AcvpStrictSessionResultItem[] } {
  return isRecord(value) && typeof value.passed === "boolean" && Array.isArray(value.results);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
