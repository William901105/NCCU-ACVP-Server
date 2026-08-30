import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  ACCESS_TOKEN_STORAGE_KEY,
  createAcvpSession,
  downloadAcvpSessionReportPdf,
  getAcvpSessionResults,
  getAcvpVectorSetPrompt,
  getAcvpVectorSetResults,
  listAcvpSessions,
  requestNewAccessToken,
  storeAccessToken,
  submitAcvpVectorSetResults
} from "./api";
import type { JsonValue } from "./types";

const VERSION = { acvVersion: "1.0" };
const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function lastRequest(): RequestInit {
  return fetchMock.mock.calls[fetchMock.mock.calls.length - 1]?.[1] ?? {};
}

function requestBody(): unknown {
  return JSON.parse(String(lastRequest().body)) as unknown;
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("localStorage", createLocalStorage());
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ACVP API", () => {
  it("gets a new token without authorization and injects it into later requests", async () => {
    const token = {
      accessToken: "test-token",
      tokenType: "Bearer" as const,
      expiresIn: 1800,
      expiresAt: new Date(Date.now() + 1_800_000).toISOString()
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse([VERSION, token]))
      .mockResolvedValueOnce(jsonResponse([VERSION, { testSessions: [] }]));

    const issued = await requestNewAccessToken();
    expect(new Headers(lastRequest().headers).get("Authorization")).toBeNull();

    storeAccessToken(issued);
    await listAcvpSessions();

    expect(new Headers(lastRequest().headers).get("Authorization")).toBe("Bearer test-token");
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toContain("test-token");
  });

  it("creates sessions with a canonical envelope rather than a bare body", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([VERSION, { testSessionId: "session-1", status: "created", vectorSetIds: [] }])
    );
    const registration = { algorithms: [{ algorithm: "ML-KEM", mode: "keyGen" }] };

    await createAcvpSession(registration);

    expect(lastRequest().method).toBe("POST");
    expect(requestBody()).toEqual([VERSION, registration]);
    expect(requestBody()).not.toEqual(registration);
  });

  it("wraps a raw IUT response in a canonical envelope and uses numeric vsId", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const response = { vsId: 42, testGroups: [] };

    await submitAcvpVectorSetResults("session-1", 42, response);

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/acvp/v1/testSessions/session-1/vectorSets/42/results"
    );
    expect(requestBody()).toEqual([VERSION, response]);
  });

  it("does not double-wrap an enveloped IUT response", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const response: JsonValue = [VERSION, { vsId: 7, testGroups: [] }];

    await submitAcvpVectorSetResults("session-1", 7, response);

    expect(requestBody()).toEqual(response);
    expect(requestBody()).toHaveLength(2);
  });

  it("handles an empty 204 result submission", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(
      submitAcvpVectorSetResults("session-1", 3, { vsId: 3, testGroups: [] })
    ).resolves.toBeUndefined();
  });

  it("preserves the raw prompt envelope", async () => {
    const prompt = { vsId: 9, algorithm: "ML-KEM", mode: "keyGen", testGroups: [] };
    fetchMock.mockResolvedValueOnce(jsonResponse([VERSION, prompt]));

    const promptView = await getAcvpVectorSetPrompt("session-1", 9);

    expect(promptView.raw).toEqual([VERSION, prompt]);
    expect(promptView.prompt).toEqual(prompt);
  });

  it("preserves raw vector and session result envelopes", async () => {
    const vectorResults = { results: { disposition: "passed", tests: [] } };
    const sessionResults = { passed: true, results: [] };
    fetchMock
      .mockResolvedValueOnce(jsonResponse([VERSION, vectorResults]))
      .mockResolvedValueOnce(jsonResponse([VERSION, sessionResults]));

    const vectorView = await getAcvpVectorSetResults("session-1", 11);
    const sessionView = await getAcvpSessionResults("session-1");

    expect(vectorView.raw).toEqual([VERSION, vectorResults]);
    expect(sessionView.raw).toEqual([VERSION, sessionResults]);
  });

  it("downloads the authenticated session report as a PDF", async () => {
    storeAccessToken({
      accessToken: "report-token",
      tokenType: "Bearer",
      expiresIn: 1800,
      expiresAt: new Date(Date.now() + 1_800_000).toISOString()
    });
    fetchMock.mockResolvedValueOnce(
      new Response(new Blob(["%PDF-1.4 report"], { type: "application/pdf" }), {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'attachment; filename="validation-report.pdf"'
        }
      })
    );

    const file = await downloadAcvpSessionReportPdf("session-1");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/acvp/v1/testSessions/session-1/reports/pdf"
    );
    expect(new Headers(lastRequest().headers).get("Authorization")).toBe(
      "Bearer report-token"
    );
    expect(new Headers(lastRequest().headers).get("Accept")).toBe("application/pdf");
    expect(file.filename).toBe("validation-report.pdf");
    expect(file.blob.type).toBe("application/pdf");
    expect(file.blob.size).toBeGreaterThan(0);
  });

  it("parses structured canonical ACVP errors", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        [
          VERSION,
          {
            error: {
              code: "NIST_GENVAL_EXECUTION_ERROR",
              message: "NIST GenVal execution failed.",
              path: "/acvp/v1/testSessions/session-1/vectorSets/1/results"
            }
          }
        ],
        500
      )
    );

    const error = await listAcvpSessions().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 500,
      code: "NIST_GENVAL_EXECUTION_ERROR",
      message: "NIST GenVal execution failed.",
      path: "/acvp/v1/testSessions/session-1/vectorSets/1/results"
    });
  });
});

function createLocalStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); }
  };
}
