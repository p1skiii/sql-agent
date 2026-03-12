import test, { afterEach } from "node:test";
import assert from "node:assert/strict";

import { POST } from "../app/api/chat/route";
import {
  errorPayload,
  readSuccessPayload,
  unsupportedPayload,
  writeCommitPayload,
  writeDryRunPayload,
} from "./fixtures/adapter-fixtures";

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
const originalFetch = globalThis.fetch;

function installFetch(payload: Record<string, unknown>, status: number) {
  globalThis.fetch = async () =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    });
}

async function postChat(body: Record<string, unknown>) {
  return POST(
    new Request("http://local/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("route returns normalized READ success with backend result preview", async () => {
  installFetch(readSuccessPayload, 200);

  const response = await postChat({
    question: "List the ids and names of all students.",
    allow_write: false,
    dry_run: true,
    force: false,
  });
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
  assert.equal(body.ok, true);
  assert.deepEqual(Object.keys(body.data).sort(), EXPECTED_SUCCESS_DATA_KEYS);
  assert.equal(body.data.mode, "READ");
  assert.equal(body.data.db_executed, true);
  assert.equal(body.data.committed, null);
  assert.equal(body.data.result.row_count, body.data.result.rows.length);
  assert.equal(body.data.result.rows[0].name, "Alice Johnson");
});

test("route returns normalized WRITE dry-run success", async () => {
  installFetch(writeDryRunPayload, 200);

  const response = await postChat({
    question: "Update the student named Alice Johnson to have GPA 3.9.",
    allow_write: true,
    dry_run: true,
    force: false,
  });
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
  assert.equal(body.ok, true);
  assert.equal(body.data.mode, "WRITE");
  assert.equal(body.data.dry_run, true);
  assert.equal(body.data.db_executed, false);
  assert.equal(body.data.committed, false);
});

test("route returns normalized WRITE commit success", async () => {
  installFetch(writeCommitPayload, 200);

  const response = await postChat({
    question: "Update the student named Alice Johnson to have GPA 3.9.",
    allow_write: true,
    dry_run: false,
    force: false,
  });
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
  assert.equal(body.ok, true);
  assert.equal(body.data.mode, "WRITE");
  assert.equal(body.data.dry_run, false);
  assert.equal(body.data.db_executed, true);
  assert.equal(body.data.committed, true);
});

test("route returns normalized UNSUPPORTED failure", async () => {
  installFetch(unsupportedPayload, 400);

  const response = await postChat({
    question: "Update the student named Alice Johnson to have GPA 3.9.",
    allow_write: true,
    dry_run: true,
    force: false,
  });
  const body = await response.json();

  assert.equal(response.status, 400);
  assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
  assert.equal(body.ok, false);
  assert.equal(body.status, "UNSUPPORTED");
  assert.equal(body.data, null);
  assert.equal(body.error?.kind, "backend");
});

test("route returns normalized backend ERROR failure", async () => {
  installFetch(errorPayload, 500);

  const response = await postChat({
    question: "Cause a backend execution error.",
    allow_write: true,
    dry_run: false,
    force: false,
  });
  const body = await response.json();

  assert.equal(response.status, 500);
  assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
  assert.equal(body.ok, false);
  assert.equal(body.status, "ERROR");
  assert.equal(body.data, null);
  assert.equal(body.error?.kind, "backend");
});

test("route returns normalized BAD_REQUEST before contacting the backend", async () => {
  const response = await postChat({});
  const body = await response.json();

  assert.equal(response.status, 400);
  assert.deepEqual(Object.keys(body).sort(), EXPECTED_TOP_LEVEL_KEYS);
  assert.equal(body.ok, false);
  assert.equal(body.status, "BAD_REQUEST");
  assert.equal(body.message, "question is required");
  assert.equal(body.data, null);
  assert.equal(body.raw, null);
});
