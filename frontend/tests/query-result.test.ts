import test from "node:test";
import assert from "node:assert/strict";

import { loadResultPreview } from "../app/api/chat/query-result";

test("loadResultPreview preserves structured rows from backend result", async () => {
  const result = await loadResultPreview({
    result: {
      columns: ["id", "name"],
      rows: [{ id: 1, name: "Alice Johnson" }],
      row_count: 1,
    },
  });

  assert.deepEqual(result, {
    columns: ["id", "name"],
    rows: [{ id: 1, name: "Alice Johnson" }],
    row_count: 1,
  });
});

test("loadResultPreview falls back to rows length when row_count is missing", async () => {
  const result = await loadResultPreview({
    result: {
      columns: ["id"],
      rows: [{ id: 1 }, { id: 2 }],
    },
  });

  assert.equal(result.row_count, 2);
});

test("loadResultPreview returns an empty preview when result is absent or malformed", async () => {
  const missing = await loadResultPreview({});
  const malformed = await loadResultPreview({
    result: {
      columns: ["id"],
      rows: [["not-an-object"]],
      row_count: 1,
    },
  });

  assert.deepEqual(missing, {
    columns: [],
    rows: [],
    row_count: 0,
  });
  assert.deepEqual(malformed, {
    columns: ["id"],
    rows: [],
    row_count: 1,
  });
});
