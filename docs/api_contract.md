# API / CLI JSON Contract (v1)

Each run emits one JSON line with the following fields (nulls allowed):

- id, dataset, db_id, config_tag, run_id, request_id
- question, sql, summary
- result {columns, rows, row_count}
- ok (bool), status, error_code, reason
- model, base_url, prompt_version, trace_version, config_hash, timestamp
- tokens (total), latency_ms
- stage_latency_ms {intent, plan, execute, summarize, other}
- stage_tokens {intent, plan, execute, summarize, other}
- guard_hit (bool), guard_rule, guard_reason
- probe_rows, affected_rows, dry_run
- repair_attempted, repair_success

Query execution endpoints:

- `POST /run`
- `POST /api/query`

Both HTTP query endpoints and CLI `--json` MUST include the same run-result schema (extra fields tolerated). All files are UTF-8 JSONL, one object per line.

Additional lightweight backend endpoints:

- `GET /api/schema`
  - Returns table metadata for the active database.
  - Shape:
    - `ok`
    - `backend`
    - `database { backend, path|url }`
    - `tables[] { name, row_count, columns[] { name, type } }`

- `GET /api/examples`
  - Returns built-in English demo questions.
  - Shape:
    - `ok`
    - `examples[] { id, question }`

- `GET /api/health`
  - Returns service and database readiness.
  - Shape:
    - `ok`
    - `status` (`healthy` or `unhealthy`)
    - `service`
    - `database { backend, ready }`
    - `config { allow_write, dry_run_default, guard_level }` on success
    - `error` on failure
