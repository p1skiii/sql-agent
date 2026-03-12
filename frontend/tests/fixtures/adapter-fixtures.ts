import type { ResultPreview } from "../../app/api/chat/normalize";

export const readSuccessPayload = {
  affected_rows: null,
  dry_run: null,
  error_code: null,
  mode: "READ",
  ok: true,
  question: "Audit sample: list student ids and names",
  raw_sql: "SELECT id, name FROM students",
  reason: null,
  repaired_sql: "SELECT id, name FROM students LIMIT 50",
  sql: "SELECT id, name FROM students LIMIT 50",
  status: "SUCCESS",
  summary: "6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore",
  trace: [
    { name: "intent_detection", preview: "READ_SIMPLE" },
    { name: "execute_sql", preview: "row_count=6" },
  ],
  result: {
    columns: ["id", "name"],
    rows: [
      { id: 1, name: "Alice Johnson" },
      { id: 2, name: "Brian Smith" },
      { id: 3, name: "Clara Lee" },
      { id: 4, name: "Daniel Green" },
      { id: 5, name: "Emily Davis" },
      { id: 6, name: "Frank Moore" },
    ],
    row_count: 6,
  },
};

export const readSuccessResult: ResultPreview = {
  columns: ["id", "name"],
  rows: [
    { id: 1, name: "Alice Johnson" },
    { id: 2, name: "Brian Smith" },
    { id: 3, name: "Clara Lee" },
    { id: 4, name: "Daniel Green" },
    { id: 5, name: "Emily Davis" },
    { id: 6, name: "Frank Moore" },
  ],
  row_count: 6,
};

export const writeDryRunPayload = {
  affected_rows: null,
  dry_run: true,
  error_code: null,
  mode: "WRITE",
  ok: true,
  question: "Audit sample: dry-run update Alice Johnson GPA to 3.9",
  raw_sql: null,
  reason: null,
  repaired_sql: null,
  sql: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
  status: "SUCCESS",
  summary: "Dry-run: would update 1 row(s)",
  trace: [
    { name: "generate_write_sql", preview: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'" },
    { name: "execute_write", preview: "affected_rows=1, dry_run=True" },
  ],
  result: { columns: [], rows: [], row_count: 0 },
};

export const writeCommitPayload = {
  affected_rows: null,
  dry_run: false,
  error_code: null,
  mode: "WRITE",
  ok: true,
  question: "Audit sample: commit update Alice Johnson GPA to 3.9",
  raw_sql: null,
  reason: null,
  repaired_sql: null,
  sql: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
  status: "SUCCESS",
  summary: "Updated 1 row(s)",
  trace: [
    { name: "generate_write_sql", preview: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'" },
    { name: "execute_write", preview: "affected_rows=1, dry_run=False" },
  ],
  result: { columns: [], rows: [], row_count: 0 },
};

export const unsupportedPayload = {
  affected_rows: null,
  diagnosis: {
    action: "review_policy",
    category: "GUARD",
    evidence: "Write operations are disabled. Use --allow-write to enable.",
  },
  dry_run: null,
  error_code: "UNSUPPORTED",
  mode: "WRITE",
  ok: false,
  question: "Audit sample: unsupported write when writes are disabled",
  raw_sql: null,
  reason: "Write operations are disabled. Use --allow-write to enable.",
  repaired_sql: null,
  sql: null,
  status: "UNSUPPORTED",
  summary: null,
  trace: [{ name: "intent_detection", preview: "WRITE" }],
};

export const errorPayload = {
  affected_rows: null,
  diagnosis: {
    action: "check_stack",
    category: "EXECUTION_ERROR",
    evidence: "no such column: missing_col",
  },
  dry_run: null,
  error_code: "ERROR",
  mode: "WRITE",
  ok: false,
  question: "Audit sample: error write with an invalid column",
  raw_sql: null,
  reason: "no such column: missing_col",
  repaired_sql: null,
  sql: null,
  status: "ERROR",
  summary: null,
  trace: [{ name: "intent_detection", preview: "WRITE" }],
};
