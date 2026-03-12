# Adapter Contract

This document defines the normalized `/api/chat` contract exposed to the frontend.

Sample artifacts:
- `frontend/samples/adapter_contract/read_success/`
- `frontend/samples/adapter_contract/write_dry_run_success/`
- `frontend/samples/adapter_contract/write_commit_success/`
- `frontend/samples/adapter_contract/unsupported/`
- `frontend/samples/adapter_contract/error/`
- `frontend/samples/adapter_contract/bad_request/`

## Stable Top-Level Shape

Every `/api/chat` response returns:

```json
{
  "ok": true,
  "http_status": 200,
  "status": "SUCCESS",
  "message": "Primary display text",
  "data": {},
  "error": null,
  "raw": {}
}
```

Top-level fields:
- `ok`: primary success boolean
- `http_status`: preserved HTTP status code
- `status`: normalized adapter status
- `message`: primary display text for all scenarios
- `data`: normalized success payload, otherwise `null`
- `error`: normalized failure payload, otherwise `null`
- `raw`: parsed upstream `/run` payload when available, otherwise `null`

Error kinds:
- `validation`: local `/api/chat` request validation
- `backend`: parsed backend `/run` failure
- `adapter`: adapter-side fetch or normalization failure

## Success Data Shape

```json
{
  "question": "List the ids and names of all students.",
  "mode": "READ",
  "summary": "6 student ids: Alice Johnson, ...",
  "sql": "SELECT id, name FROM students LIMIT 50",
  "raw_sql": "SELECT id, name FROM students",
  "repaired_sql": "SELECT id, name FROM students LIMIT 50",
  "dry_run": null,
  "db_executed": true,
  "committed": null,
  "result": {
    "columns": ["id", "name"],
    "rows": [{ "id": 1, "name": "Alice Johnson" }],
    "row_count": 1
  },
  "trace": []
}
```

Meaning:
- `message` is the primary UI text
- `data.summary` is secondary success detail
- `data.result` is the stable source for result preview tables
- `db_executed` and `committed` are the stable write/read execution semantics

## Execution Semantics

- READ success:
  - `db_executed = true`
  - `committed = null`
- WRITE dry-run success:
  - `db_executed = false`
  - `committed = false`
- WRITE commit success:
  - `db_executed = true`
  - `committed = true`

## Representative Cases

| Case | HTTP | `ok` | `status` | `data` | `error` | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| READ success | `200` | `true` | `SUCCESS` | object | `null` | `data.result` populated |
| WRITE dry-run success | `200` | `true` | `SUCCESS` | object | `null` | `db_executed=false`, `committed=false` |
| WRITE commit success | `200` | `true` | `SUCCESS` | object | `null` | `db_executed=true`, `committed=true` |
| UNSUPPORTED | `400` | `false` | `UNSUPPORTED` | `null` | object | `raw` contains parsed `/run` failure body |
| ERROR | `500` | `false` | `ERROR` | `null` | object | `raw` contains parsed `/run` failure body |
| BAD_REQUEST | `400` | `false` | `BAD_REQUEST` | `null` | object | local adapter validation, `raw=null` |

## Notes

- `message` is the default frontend display field across success and failure.
- `data.summary` is secondary success detail.
- `data.result` is the stable source for result preview; frontend should not read tabular data from `raw`.
- Real-model route checks and sample generation use the repo's configured model names through the same OpenAI-compatible proxy path at `http://localhost:4141/v1`.
