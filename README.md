# SQL Agent AMP v1

This repository now uses an AMP-style orchestration runtime with a dynamic agent pool and a two-phase task protocol.

## Core Direction

- Runtime: custom AMP orchestration (no LangChain/LangGraph execution core)
- Database support in v1: PostgreSQL only
- Capability: read + write CRUD via risk-gated workflow
- DDL policy: blocked by default and converted into proposal output
- Memory: YAML persistence under `state/memory`

## Task Protocol

### Plan

`POST /api/tasks/plan`

Input:

```json
{
  "question": "Update order status to shipped for ORD-1001",
  "session_id": "demo-session",
  "db_target": "postgres_main",
  "language": "auto"
}
```

### Confirm

`POST /api/tasks/{task_id}/confirm`

Input:

```json
{
  "approve": true,
  "comment": "approved"
}
```

### Status

`GET /api/tasks/{task_id}`

Response fields always include:

- `task_id`
- `status`
- `risk_level`
- `thinking_summary`
- `workflow`
- `result | proposal | error`
- `trace`

## Deprecated Endpoints

- `POST /run`
- `POST /api/query`

Both now return HTTP `410`.

## CLI

- `uv run sql-agent task-plan "List all users" --session-id s1`
- `uv run sql-agent task-confirm <task_id> --approve true`
- `uv run sql-agent task-show <task_id>`

## Environment

Use `.env` (see `.env.example`) and set at least:

- `SQL_AGENT_DB_BACKEND=postgres`
- `SQL_AGENT_DB_URL=postgresql+psycopg://...`
- `LLM_API_KEY=...`
- `LLM_BASE_URL=http://localhost:4141/v1` (optional)
