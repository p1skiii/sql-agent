"use client";

import { useState } from "react";

import type { NormalizedChatResponse, ResultPreview } from "./api/chat/normalize";

function statusTone(status: string): string {
  if (status === "SUCCESS") {
    return "border-emerald-400/25 bg-emerald-400/10 text-emerald-200";
  }
  if (status === "UNSUPPORTED") {
    return "border-amber-400/25 bg-amber-400/10 text-amber-200";
  }
  return "border-rose-400/25 bg-rose-400/10 text-rose-200";
}

function boolText(value: boolean | null): string {
  if (value === null) {
    return "null";
  }
  return value ? "true" : "false";
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function traceForResponse(response: NormalizedChatResponse | null): unknown[] {
  if (!response) {
    return [];
  }
  if (response.data?.trace.length) {
    return response.data.trace;
  }
  const rawTrace = response.raw?.trace;
  return Array.isArray(rawTrace) ? rawTrace : [];
}

function SqlBlock({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-muted">{label}</p>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words font-mono text-sm text-foreground">
        {value ?? "Not provided"}
      </pre>
    </div>
  );
}

function EvidenceFlag({ label, value, testId }: { label: string; value: boolean | null; testId: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-muted">{label}</p>
      <p className="mt-2 text-xl font-semibold text-foreground" data-testid={testId}>
        {boolText(value)}
      </p>
    </div>
  );
}

function ResultPreviewTable({ result }: { result: ResultPreview }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/20">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Result preview</h3>
          <p className="text-xs text-muted">Stable tabular data from `data.result`.</p>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-muted" data-testid="result-row-count">
          {result.row_count} row{result.row_count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-white/5 text-left text-xs uppercase tracking-[0.18em] text-muted">
            <tr>
              {result.columns.map((column) => (
                <th key={column} className="px-4 py-3 font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, index) => (
              <tr key={index} className="border-t border-white/10">
                {result.columns.map((column) => (
                  <td key={`${index}-${column}`} className="px-4 py-3 text-foreground/95">
                    {String(row[column] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  const [question, setQuestion] = useState("");
  const [allowWrite, setAllowWrite] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<NormalizedChatResponse | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);

  const trace = traceForResponse(response);
  const hasReadResult = Boolean(response?.data?.mode === "READ" && response.data.result.row_count > 0);
  const hasWriteEvidence = response?.data?.mode === "WRITE";

  async function submit() {
    if (!question.trim() || loading) {
      return;
    }

    setLoading(true);
    setNetworkError(null);

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          allow_write: allowWrite,
          dry_run: dryRun,
        }),
      });

      const payload = (await resp.json()) as NormalizedChatResponse;
      setResponse(payload);
    } catch (error) {
      setResponse(null);
      setNetworkError(error instanceof Error ? error.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="h-fit rounded-[28px] border border-white/10 bg-card/90 p-6 shadow-2xl shadow-black/20 backdrop-blur">
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.32em] text-sky-200/80">Phase 3</p>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">SQL Evidence Console</h1>
            <p className="text-sm leading-6 text-muted">
              One request in, one normalized `/api/chat` contract out. This page only proves the three core evidence
              flows: READ success, WRITE dry-run success, and WRITE commit success.
            </p>
          </div>

          <div className="mt-6 rounded-3xl border border-white/10 bg-black/20 p-5">
            <label className="block text-xs uppercase tracking-[0.24em] text-muted" htmlFor="question">
              Question
            </label>
            <textarea
              id="question"
              className="mt-3 h-36 w-full resize-none rounded-2xl border border-white/10 bg-card px-4 py-3 text-sm text-foreground outline-none transition focus:border-primary"
              placeholder="Ask in English, for example: List the ids and names of all students."
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />

            <div className="mt-5 space-y-3">
              <label className="flex items-center justify-between rounded-2xl border border-white/10 bg-card px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-foreground">allow_write</p>
                  <p className="text-xs text-muted">Enable write-capable requests.</p>
                </div>
                <input
                  checked={allowWrite}
                  className="h-4 w-4 accent-primary"
                  data-testid="allow-write-toggle"
                  type="checkbox"
                  onChange={(event) => setAllowWrite(event.target.checked)}
                />
              </label>

              <label className="flex items-center justify-between rounded-2xl border border-white/10 bg-card px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-foreground">dry_run</p>
                  <p className="text-xs text-muted">Probe write intent without committing.</p>
                </div>
                <input
                  checked={dryRun}
                  className="h-4 w-4 accent-primary"
                  data-testid="dry-run-toggle"
                  disabled={!allowWrite}
                  type="checkbox"
                  onChange={(event) => setDryRun(event.target.checked)}
                />
              </label>
            </div>

            <button
              className="mt-5 w-full rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              data-testid="submit-request"
              disabled={loading || !question.trim()}
              onClick={submit}
              type="button"
            >
              {loading ? "Running request..." : "Run request"}
            </button>
          </div>

          <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-muted">Result source</p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">
              READ result preview comes directly from the backend `/run` payload. The adapter normalizes it without
              doing a second database read, so the frontend contract stays stable across backend migrations.
            </p>
          </div>

          {networkError && (
            <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
              {networkError}
            </p>
          )}
        </section>

        <section className="space-y-6">
          <div className="rounded-[28px] border border-white/10 bg-card/90 p-6 shadow-2xl shadow-black/20 backdrop-blur">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
                  response ? statusTone(response.status) : "border-white/10 bg-white/5 text-muted"
                }`}
                data-testid="status-badge"
              >
                {response?.status ?? "IDLE"}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.2em] text-muted">
                HTTP {response?.http_status ?? 0}
              </span>
              {response?.data?.mode && (
                <span
                  className="rounded-full border border-sky-300/20 bg-sky-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-100"
                  data-testid="mode-badge"
                >
                  {response.data.mode}
                </span>
              )}
            </div>

            <div className="mt-5">
              <p className="text-xs uppercase tracking-[0.24em] text-muted">Message</p>
              <p className="mt-3 text-2xl font-semibold tracking-tight text-foreground" data-testid="message-text">
                {response?.message ?? "Run one of the supported scenarios to inspect the normalized evidence surfaces."}
              </p>
              {response?.data?.summary && response.data.summary !== response.message && (
                <p className="mt-3 text-sm leading-6 text-muted" data-testid="summary-text">
                  {response.data.summary}
                </p>
              )}
            </div>
          </div>

          {response && (
            <>
              <section className="rounded-[28px] border border-white/10 bg-card/90 p-6 shadow-2xl shadow-black/20 backdrop-blur" data-testid="sql-panel">
                <div className="mb-5 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-foreground">SQL panel</h2>
                    <p className="text-sm text-muted">The primary SQL evidence surface from normalized `data.*`.</p>
                  </div>
                </div>
                <div className="grid gap-4 xl:grid-cols-3">
                  <SqlBlock label="sql" value={response.data?.sql ?? null} />
                  <SqlBlock label="raw_sql" value={response.data?.raw_sql ?? null} />
                  <SqlBlock label="repaired_sql" value={response.data?.repaired_sql ?? null} />
                </div>
              </section>

              {hasReadResult && response.data && (
                <section data-testid="result-preview">
                  <ResultPreviewTable result={response.data.result} />
                </section>
              )}

              {hasWriteEvidence && response.data && (
                <section className="rounded-[28px] border border-white/10 bg-card/90 p-6 shadow-2xl shadow-black/20 backdrop-blur" data-testid="write-evidence">
                  <div className="mb-5">
                    <h2 className="text-lg font-semibold text-foreground">Write evidence</h2>
                    <p className="text-sm text-muted">Frontend-safe execution flags from the normalized adapter contract.</p>
                  </div>
                  <div className="grid gap-4 md:grid-cols-3">
                    <EvidenceFlag label="dry_run" testId="write-dry-run" value={response.data.dry_run} />
                    <EvidenceFlag label="db_executed" testId="write-db-executed" value={response.data.db_executed} />
                    <EvidenceFlag label="committed" testId="write-committed" value={response.data.committed} />
                  </div>
                </section>
              )}

              <div className="grid gap-6 xl:grid-cols-2">
                <details className="rounded-[28px] border border-white/10 bg-card/90 p-6 shadow-2xl shadow-black/20 backdrop-blur">
                  <summary className="cursor-pointer list-none text-lg font-semibold text-foreground">Raw JSON</summary>
                  <p className="mt-2 text-sm text-muted">Backend evidence payload preserved under `raw`.</p>
                  <pre className="mt-4 overflow-x-auto whitespace-pre-wrap break-words rounded-2xl border border-white/10 bg-black/25 p-4 text-xs text-foreground" data-testid="raw-json">
                    {prettyJson(response.raw ?? response)}
                  </pre>
                </details>

                <details className="rounded-[28px] border border-white/10 bg-card/90 p-6 shadow-2xl shadow-black/20 backdrop-blur">
                  <summary className="cursor-pointer list-none text-lg font-semibold text-foreground">Trace</summary>
                  <p className="mt-2 text-sm text-muted">Trace steps preserved for evidence-only inspection.</p>
                  <pre className="mt-4 overflow-x-auto whitespace-pre-wrap break-words rounded-2xl border border-white/10 bg-black/25 p-4 text-xs text-foreground" data-testid="trace-json">
                    {prettyJson(trace)}
                  </pre>
                </details>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
