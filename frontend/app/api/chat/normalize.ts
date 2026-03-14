export type ChatStatus = "SUCCESS" | "UNSUPPORTED" | "ERROR" | "BAD_REQUEST" | string;

export type ResultRow = Record<string, unknown>;

export interface ResultPreview {
  columns: string[];
  rows: ResultRow[];
  row_count: number;
}

export interface NormalizedChatData {
  question: string;
  mode: "READ" | "WRITE";
  summary: string | null;
  sql: string | null;
  raw_sql: string | null;
  repaired_sql: string | null;
  dry_run: boolean | null;
  db_executed: boolean;
  committed: boolean | null;
  result: ResultPreview;
  before_result?: ResultPreview | null;
  trace: unknown[];
}

export interface NormalizedChatError {
  kind: "validation" | "backend" | "adapter";
  message: string;
  code: string;
}

export interface NormalizedChatResponse {
  ok: boolean;
  http_status: number;
  status: ChatStatus;
  message: string;
  data: NormalizedChatData | null;
  error: NormalizedChatError | null;
  raw: Record<string, unknown> | null;
}

type UpstreamPayload = Record<string, unknown>;

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function booleanOrNull(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function arrayOrEmpty(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function objectOrNull(value: unknown): UpstreamPayload | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UpstreamPayload)
    : null;
}

function messageFromPayload(payload: UpstreamPayload | null, fallback: string): string {
  return stringOrNull(payload?.summary) ?? stringOrNull(payload?.reason) ?? stringOrNull(payload?.error) ?? fallback;
}

function statusFromPayload(payload: UpstreamPayload | null, fallback: ChatStatus): ChatStatus {
  return stringOrNull(payload?.status) ?? fallback;
}

function codeFromPayload(payload: UpstreamPayload | null, fallback: string): string {
  return stringOrNull(payload?.error_code) ?? stringOrNull(payload?.status) ?? fallback;
}

function computeDbExecuted(mode: "READ" | "WRITE", dryRun: boolean | null): boolean {
  if (mode === "READ") {
    return true;
  }
  return dryRun === false;
}

function computeCommitted(mode: "READ" | "WRITE", dryRun: boolean | null): boolean | null {
  if (mode === "READ") {
    return null;
  }
  return dryRun === false;
}

export function parseUpstreamPayload(text: string): UpstreamPayload | null {
  try {
    return objectOrNull(JSON.parse(text));
  } catch {
    return null;
  }
}

export function normalizeValidationFailure(message: string, httpStatus = 400): NormalizedChatResponse {
  return {
    ok: false,
    http_status: httpStatus,
    status: "BAD_REQUEST",
    message,
    data: null,
    error: {
      kind: "validation",
      message,
      code: "BAD_REQUEST",
    },
    raw: null,
  };
}

export function normalizeBackendSuccess(
  httpStatus: number,
  payload: UpstreamPayload,
  result: ResultPreview,
): NormalizedChatResponse {
  const mode = stringOrNull(payload.mode) === "WRITE" ? "WRITE" : "READ";
  const dryRun = booleanOrNull(payload.dry_run);
  const message = messageFromPayload(payload, "No response");
  const summary = stringOrNull(payload.summary);

  const beforeResult = (payload.before_result as ResultPreview) || null;

  return {
    ok: true,
    http_status: httpStatus,
    status: statusFromPayload(payload, "SUCCESS"),
    message,
    data: {
      question: stringOrNull(payload.question) ?? "",
      mode,
      summary,
      sql: stringOrNull(payload.sql),
      raw_sql: stringOrNull(payload.raw_sql),
      repaired_sql: stringOrNull(payload.repaired_sql),
      dry_run: dryRun,
      db_executed: computeDbExecuted(mode, dryRun),
      committed: computeCommitted(mode, dryRun),
      result,
      ...(beforeResult ? { before_result: beforeResult } : {}),
      trace: arrayOrEmpty(payload.trace),
    },
    error: null,
    raw: payload,
  };
}

export function normalizeBackendFailure(
  httpStatus: number,
  payload: UpstreamPayload | null,
  fallbackMessage: string,
): NormalizedChatResponse {
  const message = messageFromPayload(payload, fallbackMessage);
  const fallbackStatus: ChatStatus = "ERROR";

  return {
    ok: false,
    http_status: httpStatus,
    status: statusFromPayload(payload, fallbackStatus),
    message,
    data: null,
    error: {
      kind: "backend",
      message,
      code: codeFromPayload(payload, fallbackStatus),
    },
    raw: payload,
  };
}

export function normalizeAdapterFailure(
  message: string,
  httpStatus = 500,
  raw: UpstreamPayload | null = null,
): NormalizedChatResponse {
  return {
    ok: false,
    http_status: httpStatus,
    status: "ERROR",
    message,
    data: null,
    error: {
      kind: "adapter",
      message,
      code: "ERROR",
    },
    raw,
  };
}

export function emptyResultPreview(): ResultPreview {
  return {
    columns: [],
    rows: [],
    row_count: 0,
  };
}
