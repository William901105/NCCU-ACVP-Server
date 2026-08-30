import type { AcvpEnvelope, AcvpVersion } from "./types";

export const ACVP_VERSION: AcvpVersion = "1.0";

export function acvpEnvelope<T>(body: T): AcvpEnvelope<T> {
  return [{ acvVersion: ACVP_VERSION }, body];
}

export function isAcvpEnvelope(payload: unknown): payload is AcvpEnvelope<unknown> {
  if (!Array.isArray(payload) || payload.length !== 2) {
    return false;
  }
  const version = payload[0];
  const body = payload[1];
  return (
    isRecord(version) &&
    Object.keys(version).length === 1 &&
    version.acvVersion === ACVP_VERSION &&
    isRecord(body)
  );
}

export function unwrapAcvpEnvelope<T>(payload: unknown): T {
  return (isAcvpEnvelope(payload) ? payload[1] : payload) as T;
}

export function downloadJson(value: unknown, filename: string): void {
  const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], {
    type: "application/json"
  });
  downloadBlob(blob, filename);
}

export function downloadBlob(blob: Blob, filename: string): void {
  const safeFilename = sanitizeFilename(filename);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = safeFilename;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}

export function sanitizeFilename(value: string): string {
  const sanitized = value.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return sanitized || "acvp-report";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
