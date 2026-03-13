import { NextResponse } from "next/server";

import {
  normalizeAdapterFailure,
  normalizeBackendFailure,
  normalizeBackendSuccess,
  normalizeValidationFailure,
  parseUpstreamPayload,
} from "./normalize";
import { loadResultPreview } from "./query-result";

function backendRunUrl(): string {
  return process.env.SQL_AGENT_RUN_URL ?? "http://localhost:8000/run";
}

function booleanField(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    const normalized = normalizeValidationFailure("invalid JSON body");
    return NextResponse.json(normalized, { status: normalized.http_status });
  }

  const question = body?.question;
  if (!question || typeof question !== "string") {
    const normalized = normalizeValidationFailure("question is required");
    return NextResponse.json(normalized, { status: normalized.http_status });
  }

  let resp: Response;
  try {
    resp = await fetch(backendRunUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        allow_write: booleanField(body.allow_write, false),
        dry_run: booleanField(body.dry_run, true),
        force: booleanField(body.force, false),
      }),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to reach backend /run";
    const normalized = normalizeAdapterFailure(message);
    return NextResponse.json(normalized, { status: normalized.http_status });
  }

  if (!resp.ok) {
    const text = await resp.text();
    const normalized = normalizeBackendFailure(resp.status, parseUpstreamPayload(text), text || resp.statusText);
    return NextResponse.json(normalized, { status: resp.status });
  }

  try {
    const payload = (await resp.json()) as Record<string, unknown>;
    const result = await loadResultPreview(payload);
    const normalized = normalizeBackendSuccess(resp.status, payload, result);
    return NextResponse.json(normalized, { status: resp.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Adapter failed to normalize backend response";
    const normalized = normalizeAdapterFailure(message);
    return NextResponse.json(normalized, { status: normalized.http_status });
  }
}
