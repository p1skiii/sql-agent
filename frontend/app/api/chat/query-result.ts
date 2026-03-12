import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

import { emptyResultPreview, type ResultPreview, type ResultRow } from "./normalize";

const execFileAsync = promisify(execFile);

type UpstreamPayload = Record<string, unknown>;

function resolveRepoRoot(): string {
  const envRoot = process.env.SQL_AGENT_REPO_ROOT;
  const candidates = [envRoot, process.cwd(), path.resolve(process.cwd(), "..")].filter(Boolean) as string[];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "pyproject.toml"))) {
      return candidate;
    }
  }
  return path.resolve(process.cwd(), "..");
}

function resolveDbPath(repoRoot: string): string {
  if (process.env.SQL_AGENT_DB_PATH) {
    return process.env.SQL_AGENT_DB_PATH;
  }

  const candidates = [
    path.join(repoRoot, "sandbox", "sandbox.db"),
    path.join(repoRoot, "..", "sandbox", "sandbox.db"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return candidates[0];
}

function isReadSuccess(payload: UpstreamPayload): boolean {
  const mode = typeof payload.mode === "string" ? payload.mode : "";
  const sql = typeof payload.sql === "string" ? payload.sql.trim().toLowerCase() : "";
  return mode === "READ" && sql.startsWith("select");
}

function coerceResultRows(value: unknown): ResultRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((row): row is ResultRow => row !== null && typeof row === "object" && !Array.isArray(row));
}

export async function loadResultPreview(payload: UpstreamPayload): Promise<ResultPreview> {
  if (!isReadSuccess(payload) || typeof payload.sql !== "string") {
    return emptyResultPreview();
  }

  const repoRoot = resolveRepoRoot();
  const dbPath = resolveDbPath(repoRoot);
  const scriptPath = path.join(repoRoot, "scripts", "query_sqlite_json.py");
  const { stdout } = await execFileAsync(
    "uv",
    ["run", "python", scriptPath, "--db-path", dbPath, "--sql", payload.sql],
    { cwd: repoRoot },
  );

  const parsed = JSON.parse(stdout.trim()) as {
    columns?: unknown;
    rows?: unknown;
    row_count?: unknown;
  };

  const columns = Array.isArray(parsed.columns)
    ? parsed.columns.filter((value): value is string => typeof value === "string")
    : [];
  const rows = coerceResultRows(parsed.rows);
  const rowCount = typeof parsed.row_count === "number" ? parsed.row_count : rows.length;

  return {
    columns,
    rows,
    row_count: rowCount,
  };
}
