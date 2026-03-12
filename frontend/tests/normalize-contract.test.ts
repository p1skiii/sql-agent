import test from "node:test";
import assert from "node:assert/strict";

import { emptyResultPreview, normalizeBackendFailure, normalizeBackendSuccess, normalizeValidationFailure } from "../app/api/chat/normalize";
import {
  errorPayload,
  readSuccessPayload,
  readSuccessResult,
  unsupportedPayload,
  writeCommitPayload,
  writeDryRunPayload,
} from "./fixtures/adapter-fixtures";

test("normalize read success into stable contract", () => {
  const response = normalizeBackendSuccess(200, readSuccessPayload, readSuccessResult);

  assert.equal(response.http_status, 200);
  assert.equal(response.ok, true);
  assert.equal(response.status, "SUCCESS");
  assert.equal(response.message, readSuccessPayload.summary);
  assert.equal(response.error, null);
  assert.ok(response.data);
  assert.equal(response.data.mode, "READ");
  assert.equal(response.data.db_executed, true);
  assert.equal(response.data.committed, null);
  assert.deepEqual(response.data.result, readSuccessResult);
  assert.equal(response.data.result.row_count, response.data.result.rows.length);
});

test("normalize write dry-run success into stable contract", () => {
  const response = normalizeBackendSuccess(200, writeDryRunPayload, emptyResultPreview());

  assert.equal(response.http_status, 200);
  assert.equal(response.ok, true);
  assert.equal(response.status, "SUCCESS");
  assert.ok(response.data);
  assert.equal(response.data.mode, "WRITE");
  assert.equal(response.data.dry_run, true);
  assert.equal(response.data.db_executed, false);
  assert.equal(response.data.committed, false);
  assert.equal(response.data.result.row_count, 0);
});

test("normalize write commit success into stable contract", () => {
  const response = normalizeBackendSuccess(200, writeCommitPayload, emptyResultPreview());

  assert.equal(response.http_status, 200);
  assert.equal(response.ok, true);
  assert.ok(response.data);
  assert.equal(response.data.mode, "WRITE");
  assert.equal(response.data.dry_run, false);
  assert.equal(response.data.db_executed, true);
  assert.equal(response.data.committed, true);
  assert.equal(response.data.result.row_count, 0);
});

test("normalize unsupported failure into stable contract", () => {
  const response = normalizeBackendFailure(400, unsupportedPayload, unsupportedPayload.reason ?? "Unsupported");

  assert.equal(response.http_status, 400);
  assert.equal(response.ok, false);
  assert.equal(response.status, "UNSUPPORTED");
  assert.equal(response.message, unsupportedPayload.reason);
  assert.equal(response.data, null);
  assert.equal(response.error?.kind, "backend");
  assert.equal(response.error?.code, "UNSUPPORTED");
  assert.deepEqual(response.raw, unsupportedPayload);
});

test("normalize execution error into stable contract", () => {
  const response = normalizeBackendFailure(500, errorPayload, errorPayload.reason ?? "Error");

  assert.equal(response.http_status, 500);
  assert.equal(response.ok, false);
  assert.equal(response.status, "ERROR");
  assert.equal(response.message, errorPayload.reason);
  assert.equal(response.data, null);
  assert.equal(response.error?.kind, "backend");
  assert.equal(response.error?.code, "ERROR");
  assert.deepEqual(response.raw, errorPayload);
});

test("normalize local validation failure into stable contract", () => {
  const response = normalizeValidationFailure("question is required");

  assert.equal(response.http_status, 400);
  assert.equal(response.ok, false);
  assert.equal(response.status, "BAD_REQUEST");
  assert.equal(response.message, "question is required");
  assert.equal(response.data, null);
  assert.equal(response.raw, null);
  assert.deepEqual(response.error, {
    kind: "validation",
    message: "question is required",
    code: "BAD_REQUEST",
  });
});
