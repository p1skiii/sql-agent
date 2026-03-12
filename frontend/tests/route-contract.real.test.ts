import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

const REPO_ROOT = path.resolve(process.cwd(), "..");

let backendProc: ChildProcessWithoutNullStreams | null = null;
let tempDir = "";
let dbPath = "";
let backendPort = 0;
let backendUrl = "";
let backendStdout = "";
let backendStderr = "";
const EXPECTED_TOP_LEVEL_KEYS = ["ok", "http_status", "status", "message", "data", "error", "raw"].sort();
const EXPECTED_SUCCESS_DATA_KEYS = [
  "question",
  "mode",
  "summary",
  "sql",
  "raw_sql",
  "repaired_sql",
  "dry_run",
  "db_executed",
  "committed",
  "result",
  "trace",
].sort();

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
      const resp = await fetch(backendUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (resp.status >= 400) {
        return;
      }
    } catch {
      // keep polling
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Timed out waiting for real-model backend");
}

async function loadRoute() {
  process.env.SQL_AGENT_RUN_URL = backendUrl;
  process.env.SQL_AGENT_DB_PATH = dbPath;
  process.env.SQL_AGENT_REPO_ROOT = REPO_ROOT;
  return import("../app/api/chat/route");
}

before(async () => {
  tempDir = await mkdtemp(path.join(os.tmpdir(), "adapter-contract-"));
  dbPath = path.join(tempDir, "route-contract.db");
  backendPort = await reservePort();
  backendUrl = `http://127.0.0.1:${backendPort}/run`;

  backendProc = spawn(
    "uv",
    ["run", "python", "-m", "sql_agent_demo.interfaces.api", "--host", "127.0.0.1", "--port", String(backendPort)],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        LLM_BASE_URL: "http://localhost:4141/v1",
        LLM_API_KEY: "dummy",
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
});

after(async () => {
  if (backendProc && backendProc.exitCode === null) {
    backendProc.kill("SIGTERM");
    await new Promise((resolve) => backendProc?.once("exit", resolve));
  }
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test(
  "route returns normalized READ success with result preview using the minimal real-model regression path",
  { timeout: 120_000 },
  async () => {
    const { POST } = await loadRoute();
    const response = await POST(
      new Request("http://local/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "List the ids and names of all students.",
          allow_write: false,
          dry_run: true,
          force: false,
        }),
      }),
    );
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
    assert.equal(body.ok, true);
    assert.equal(body.http_status, 200);
    assert.equal(body.status, "SUCCESS");
    assert.deepEqual(Object.keys(body.data).sort(), EXPECTED_SUCCESS_DATA_KEYS);
    assert.equal(body.data.mode, "READ");
    assert.equal(body.data.db_executed, true);
    assert.equal(body.data.committed, null);
    assert.ok(Array.isArray(body.data.result.columns));
    assert.ok(Array.isArray(body.data.result.rows));
    assert.equal(body.data.result.row_count, body.data.result.rows.length);
    assert.ok(body.raw?.result);
  },
);
