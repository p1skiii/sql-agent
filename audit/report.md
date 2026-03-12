# Response Audit Report

Generated from deterministic request/reply samples captured through the real `/run` Flask route and the real `/api/chat` Next route.

## Sample Inventory
| Sample | Request payload | `/run` status | `/api/chat` status | Notes |
| --- | --- | --- | --- | --- |
| `read_success` | `{"question": "Audit sample: list student ids and names", "allow_write": false, "dry_run": true, "force": false}` | 200 | 200 | Baseline READ success sample. |
| `write_dry_run_success` | `{"question": "Audit sample: dry-run update Alice Johnson GPA to 3.9", "allow_write": true, "dry_run": true, "force": false}` | 200 | 200 | Guarded WRITE dry-run success sample. |
| `write_commit_success` | `{"question": "Audit sample: commit update Alice Johnson GPA to 3.9", "allow_write": true, "dry_run": false, "force": false}` | 200 | 200 | Guarded WRITE commit success sample with before/after verification. |
| `unsupported` | `{"question": "Audit sample: unsupported write when writes are disabled", "allow_write": false, "dry_run": true, "force": false}` | 400 | 400 | Business-policy rejection path with TaskStatus.UNSUPPORTED. |
| `error` | `{"question": "Audit sample: error write with an invalid column", "allow_write": true, "dry_run": true, "force": false}` | 500 | 500 | Execution error path with TaskStatus.ERROR. |
| `bad_request_validation` | `{}` | 400 | 400 | Direct API validation error path outside result_to_json. |

## HTTP Behavior
| Sample | Route | Status | Content-Type | Body shape |
| --- | --- | --- | --- | --- |
| `read_success` | `/run` | 200 | `application/json` | `affected_rows, dry_run, error_code, mode, ok, question, raw_sql, reason, repaired_sql, sql, status, summary, trace` |
| `read_success` | `/api/chat` | 200 | `application/json` | `raw, summary` |
| `write_dry_run_success` | `/run` | 200 | `application/json` | `affected_rows, dry_run, error_code, mode, ok, question, raw_sql, reason, repaired_sql, sql, status, summary, trace` |
| `write_dry_run_success` | `/api/chat` | 200 | `application/json` | `raw, summary` |
| `write_commit_success` | `/run` | 200 | `application/json` | `affected_rows, dry_run, error_code, mode, ok, question, raw_sql, reason, repaired_sql, sql, status, summary, trace` |
| `write_commit_success` | `/api/chat` | 200 | `application/json` | `raw, summary` |
| `unsupported` | `/run` | 400 | `application/json` | `affected_rows, diagnosis, dry_run, error_code, mode, ok, question, raw_sql, reason, repaired_sql, sql, status, summary, trace` |
| `unsupported` | `/api/chat` | 400 | `application/json` | `error` |
| `error` | `/run` | 500 | `application/json` | `affected_rows, diagnosis, dry_run, error_code, mode, ok, question, raw_sql, reason, repaired_sql, sql, status, summary, trace` |
| `error` | `/api/chat` | 500 | `application/json` | `error` |
| `bad_request_validation` | `/run` | 400 | `application/json` | `error, ok` |
| `bad_request_validation` | `/api/chat` | 400 | `application/json` | `error` |

Key observations:
- `/run` success returns HTTP 200 with the `result_to_json(...)` shape.
- `/run` unsupported returns HTTP 400 with the same `result_to_json(...)` envelope.
- `/run` execution error returns HTTP 500 with the same `result_to_json(...)` envelope.
- `/run` bad request validation returns HTTP 400 with a different direct body: `{ok:false,error:...}`.
- `/api/chat` success returns HTTP 200 with `{summary, raw}`.
- `/api/chat` has its own request validation for missing `question`, returning HTTP 400 with a minimal `{error}` body before any backend call.
- For backend-proxied failures, `/api/chat` mirrors the backend status code but wraps the entire backend JSON body into a string field: `{error: "...raw backend JSON..."}`.

## `/run` Field Inventory
| Field | Presence | Observed type | Example value | Notes |
| --- | --- | --- | --- | --- |
| `affected_rows` | conditional | `null` | `null` | Observed as null in every sampled write response. |
| `diagnosis` | conditional | `object` | `{"action": "review_policy", "category": "GUARD", "evidence": "Write operations are disabled. Use --allow-write to enable."}` |  |
| `dry_run` | conditional | `boolean | null` | `null` |  |
| `error` | conditional | `string` | `"question is required"` | String content is not shape-stable: plain message for local validation, serialized backend JSON for proxied failures. |
| `error_code` | conditional | `null | string` | `null` |  |
| `mode` | conditional | `string` | `"READ"` |  |
| `ok` | always | `boolean` | `true` |  |
| `question` | conditional | `string` | `"Audit sample: list student ids and names"` |  |
| `raw_sql` | conditional | `null | string` | `"SELECT id, name FROM students"` |  |
| `reason` | conditional | `null | string` | `null` |  |
| `repaired_sql` | conditional | `null | string` | `"SELECT id, name FROM students LIMIT 50"` |  |
| `sql` | conditional | `null | string` | `"SELECT id, name FROM students LIMIT 50"` |  |
| `status` | conditional | `string` | `"SUCCESS"` |  |
| `summary` | conditional | `null | string` | `"6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore"` |  |
| `trace` | conditional | `array` | `[{"completion_tokens": null, "duration_ms": null, "name": "intent_detection", "notes": null, "preview": "READ_SIMPLE", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "load_schema", "notes": null, "preview": "enrollments(id, student_id, course_id, grade)\nstudents(id, name, city, major, gpa)", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "guard_config", "notes": null, "preview": "guard_level=strict", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "shape_sql", "notes": "limit 50", "preview": "SELECT id, name FROM students LIMIT 50", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "generate_sql", "notes": null, "preview": "SELECT id, name FROM students LIMIT 50", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "execute_sql", "notes": null, "preview": "row_count=6", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "summarize", "notes": null, "preview": "6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}]` |  |
| `id` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `dataset` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `db_id` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `config_tag` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `run_id` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `request_id` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `model` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `base_url` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `prompt_version` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `trace_version` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `config_hash` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `timestamp` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `tokens` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `latency_ms` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `stage_latency_ms` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `stage_tokens` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `guard_hit` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `guard_rule` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `guard_reason` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `probe_rows` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `repair_attempted` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |
| `repair_success` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |

## `/api/chat` Top-Level Field Inventory
| Field | Presence | Observed type | Example value | Notes |
| --- | --- | --- | --- | --- |
| `error` | conditional | `string` | `"{\"affected_rows\":null,\"diagnosis\":{\"action\":\"review_policy\",\"category\":\"GUARD\",\"evidence\":\"Write operations are disabled. Use --allow-write to enable.\"},\"dry_run\":null,\"error_code\":\"UNSUPPORTED\",\"mode\":\"WRITE\",\"ok\":false,\"question\":\"Audit sample: unsupported write when writes are disabled\",\"raw_sql\":null,\"reason\":\"Write operations are disabled. Use --allow-write to enable.\",\"repaired_sql\":null,\"sql\":null,\"status\":\"UNSUPPORTED\",\"summary\":null,\"trace\":[{\"completion_tokens\":null,\"duration_ms\":null,\"name\":\"intent_detection\",\"notes\":null,\"preview\":\"WRITE\",\"prompt_tokens\":null,\"severity\":\"INFO\",\"total_tokens\":null}]}\n"` | String content is not shape-stable: plain message for local validation, serialized backend JSON for proxied failures. |
| `raw` | conditional | `object` | `{"affected_rows": null, "dry_run": null, "error_code": null, "mode": "READ", "ok": true, "question": "Audit sample: list student ids and names", "raw_sql": "SELECT id, name FROM students", "reason": null, "repaired_sql": "SELECT id, name FROM students LIMIT 50", "sql": "SELECT id, name FROM students LIMIT 50", "status": "SUCCESS", "summary": "6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore", "trace": [{"completion_tokens": null, "duration_ms": null, "name": "intent_detection", "notes": null, "preview": "READ_SIMPLE", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "load_schema", "notes": null, "preview": "enrollments(id, student_id, course_id, grade)\nstudents(id, name, city, major, gpa)", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "guard_config", "notes": null, "preview": "guard_level=strict", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "shape_sql", "notes": "limit 50", "preview": "SELECT id, name FROM students LIMIT 50", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "generate_sql", "notes": null, "preview": "SELECT id, name FROM students LIMIT 50", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "execute_sql", "notes": null, "preview": "row_count=6", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "summarize", "notes": null, "preview": "6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}]}` |  |
| `summary` | conditional | `string` | `"6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore"` |  |

## `/api/chat.raw` Field Inventory
This section covers success-only `raw` objects. Failure responses do not include `raw` at all.
| Field | Presence | Observed type | Example value | Notes |
| --- | --- | --- | --- | --- |
| `affected_rows` | always | `null` | `null` | Observed as null in every sampled write response. |
| `dry_run` | always | `boolean | null` | `null` |  |
| `error_code` | always | `null` | `null` |  |
| `mode` | always | `string` | `"READ"` |  |
| `ok` | always | `boolean` | `true` |  |
| `question` | always | `string` | `"Audit sample: list student ids and names"` |  |
| `raw_sql` | always | `null | string` | `"SELECT id, name FROM students"` |  |
| `reason` | always | `null` | `null` |  |
| `repaired_sql` | always | `null | string` | `"SELECT id, name FROM students LIMIT 50"` |  |
| `sql` | always | `string` | `"SELECT id, name FROM students LIMIT 50"` |  |
| `status` | always | `string` | `"SUCCESS"` |  |
| `summary` | always | `string` | `"6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore"` |  |
| `trace` | always | `array` | `[{"completion_tokens": null, "duration_ms": null, "name": "intent_detection", "notes": null, "preview": "READ_SIMPLE", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "load_schema", "notes": null, "preview": "enrollments(id, student_id, course_id, grade)\nstudents(id, name, city, major, gpa)", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "guard_config", "notes": null, "preview": "guard_level=strict", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "shape_sql", "notes": "limit 50", "preview": "SELECT id, name FROM students LIMIT 50", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "generate_sql", "notes": null, "preview": "SELECT id, name FROM students LIMIT 50", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "execute_sql", "notes": null, "preview": "row_count=6", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}, {"completion_tokens": null, "duration_ms": null, "name": "summarize", "notes": null, "preview": "6 student ids: Alice Johnson, Brian Smith, Clara Lee, Daniel Green, Emily Davis, Frank Moore", "prompt_tokens": null, "severity": "INFO", "total_tokens": null}]` |  |

## Write Commit Evidence
- Before commit: `[{"name": "Alice Johnson", "gpa": 3.8}]`
- Verification read summary: `1 gpa: 3.9` with status `200`
- After commit DB rows: `[{"name": "Alice Johnson", "gpa": 3.9}]`

## Current Mismatches
- `docs/api_contract.md` documents many fields that do not appear in the sampled runtime `/run` bodies.
- `/api/chat` drops stable top-level backend fields on success and exposes them only under `raw`.
- `/api/chat` does not preserve the backend JSON envelope on failure; it stringifies the full backend body into `error`.
- `affected_rows` stays `null` in all sampled write-success `/run` bodies even when writes clearly affect one row.

## Recommended Display Contract

### Result Card: always safe now
- `/api/chat` success: `summary`
- `/api/chat` failure: `error`
- `/api/chat` success-only raw state when present: `raw.status`, `raw.mode`, `raw.reason`

### SQL Panel: safe only when present
- `raw.sql`
- `raw.raw_sql`
- `raw.repaired_sql`

### Write Evidence: safe only with verification
- `audit/samples/write_commit_success/db_before.json`
- `audit/samples/write_commit_success/db_after.json`
- `audit/samples/write_commit_success/verification_read.json`

### Trace Panel: safe but optional
- `raw.trace`

### UI Must Not Rely On
- `raw.affected_rows` exactness
- `raw.diagnosis` completeness
- `raw.repaired_sql` existence
- a single top-level `/api/chat` shape for both success and failure
