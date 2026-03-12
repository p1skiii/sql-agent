import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

import { normalizeBackendFailure, normalizeValidationFailure } from "../app/api/chat/normalize";
import { errorPayload, unsupportedPayload } from "../tests/fixtures/adapter-fixtures";

const FRONTEND_ROOT = process.cwd();
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");
const SAMPLES_ROOT = path.join(FRONTEND_ROOT, "samples", "adapter_contract");

let backendProc: ChildProcessWithoutNullStreams | null = null;
let backendStdout = "";
let backendStderr = "";
let tempDir = "";
let dbPath = "";
let backendUrl = "";

function stableStringify(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

async function reservePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("Failed to reserve a backend port"));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

async function waitForBackend(): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (backendProc?.exitCode !== null && backendProc?.exitCode !== undefined) {
      throw new Error(`Real-model backend exited during startup (${backendProc.exitCode}): ${backendStderr || backendStdout || "no output"}`);
    }
    try {
      const response = await fetch(backendUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (response.status >= 400) {
        return;
      }
    } catch {
      // Keep polling until the backend starts or exits.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for real-model backend: ${backendStderr || backendStdout || "no output"}`);
}

async function startBackend(): Promise<void> {
  tempDir = await mkdtemp(path.join(os.tmpdir(), "adapter-samples-"));
  dbPath = path.join(tempDir, "adapter-samples.db");
  const backendPort = await reservePort();
  backendUrl = `http://127.0.0.1:${backendPort}/run`;

  backendProc = spawn(
    "uv",
    ["run", "--extra", "openai", "python", "-m", "sql_agent_demo.interfaces.api", "--host", "127.0.0.1", "--port", String(backendPort)],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        LLM_BASE_URL: process.env.LLM_BASE_URL ?? "http://localhost:4141/v1",
        LLM_API_KEY: process.env.LLM_API_KEY ?? "dummy",
        LLM_USE_SLIM: process.env.LLM_USE_SLIM ?? "1",
        SQL_AGENT_DB_PATH: dbPath,
        SQL_AGENT_SCHEMA_PATH: path.join(REPO_ROOT, "tests", "data", "schema.sql"),
        SQL_AGENT_SEED_PATH: path.join(REPO_ROOT, "tests", "data", "seed.sql"),
        SQL_AGENT_OVERWRITE_DB: "true",
        SQL_AGENT_ALLOW_TRACE: "true",
        SQL_AGENT_INTENT_MODEL: process.env.SQL_AGENT_INTENT_MODEL ?? "gpt-4o-mini",
        SQL_AGENT_SQL_MODEL: process.env.SQL_AGENT_SQL_MODEL ?? "gpt-4o-mini",
      },
      stdio: "pipe",
    },
  );

  backendProc.stdout.on("data", (chunk) => {
    backendStdout += chunk.toString();
  });
  backendProc.stderr.on("data", (chunk) => {
    backendStderr += chunk.toString();
  });

  await waitForBackend();
}

async function stopBackend(): Promise<void> {
  if (backendProc && backendProc.exitCode === null) {
    backendProc.kill("SIGTERM");
    await new Promise((resolve) => backendProc?.once("exit", resolve));
  }
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
  }
}

async function loadRoute() {
  process.env.SQL_AGENT_RUN_URL = backendUrl;
  process.env.SQL_AGENT_DB_PATH = dbPath;
  process.env.SQL_AGENT_REPO_ROOT = REPO_ROOT;
  return import("../app/api/chat/route");
}

async function writeSample(name: string, requestBody: Record<string, unknown>, responseBody: unknown): Promise<void> {
  const sampleDir = path.join(SAMPLES_ROOT, name);
  await mkdir(sampleDir, { recursive: true });
  await writeFile(path.join(sampleDir, "request.json"), stableStringify(requestBody));
  await writeFile(path.join(sampleDir, "response.json"), stableStringify(responseBody));
}

async function captureLiveRouteSample(
  post: (request: Request) => Promise<Response>,
  name: string,
  requestBody: Record<string, unknown>,
): Promise<void> {
  const response = await post(
    new Request("http://local/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    }),
  );
  const body = await response.json();
  await writeSample(name, requestBody, body);
}

async function main(): Promise<void> {
  await mkdir(SAMPLES_ROOT, { recursive: true });
  await startBackend();

  try {
    const { POST } = await loadRoute();

    await captureLiveRouteSample(POST, "read_success", {
      question: "List the ids and names of all students.",
      allow_write: false,
      dry_run: true,
      force: false,
    });

    await captureLiveRouteSample(POST, "write_dry_run_success", {
      question: "Update the student named Alice Johnson to have GPA 3.9.",
      allow_write: true,
      dry_run: true,
      force: false,
    });

    await captureLiveRouteSample(POST, "write_commit_success", {
      question: "Update the student named Alice Johnson to have GPA 3.9.",
      allow_write: true,
      dry_run: false,
      force: false,
    });

    await writeSample(
      "unsupported",
      {
        question: unsupportedPayload.question,
        allow_write: false,
        dry_run: true,
        force: false,
      },
      normalizeBackendFailure(400, unsupportedPayload, unsupportedPayload.reason ?? "Unsupported"),
    );

    await writeSample(
      "error",
      {
        question: errorPayload.question,
        allow_write: true,
        dry_run: false,
        force: false,
      },
      normalizeBackendFailure(500, errorPayload, errorPayload.reason ?? "Error"),
    );

    await writeSample("bad_request", {}, normalizeValidationFailure("question is required"));
  } finally {
    await stopBackend();
  }
}

await main();
