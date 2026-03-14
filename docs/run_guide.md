# Run Guide

## Quick Start
1. Install dependencies:
   ```bash
   uv sync
   pnpm --dir frontend install
   ```
2. Create your runtime env:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set at least `LLM_API_KEY`. The documented path assumes `LLM_BASE_URL=http://localhost:4141/v1`.
3. Start PostgreSQL:
   ```bash
   docker compose -f docker-compose.postgres.yml up -d postgres
   ```
4. Start the backend for the business-demo path:
   ```bash
   uv run sql-agent-api --host 127.0.0.1 --port 8000
   ```
5. Start the frontend and verify one request:
   ```bash
   SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run pnpm --dir frontend dev --hostname 127.0.0.1 --port 3000
   ```
   Then open `http://127.0.0.1:3000`.

## Full Run Guide

### Runtime Variables

| Variable | Used by | Required | Default / meaning |
| --- | --- | --- | --- |
| `LLM_API_KEY` | backend | yes | API key or proxy token for the OpenAI-compatible endpoint |
| `LLM_BASE_URL` | backend | no | Documented default is `http://localhost:4141/v1` |
| `SQL_AGENT_DB_BACKEND` | backend | no | `postgres` for the business demo, `sqlite` for the experiment path |
| `SQL_AGENT_DB_URL` | backend | required for PostgreSQL | PostgreSQL DSN |
| `SQL_AGENT_DB_PATH` | backend | required for SQLite fallback | SQLite file path |
| `SQL_AGENT_SCHEMA_PATH` | backend | no | Schema SQL path |
| `SQL_AGENT_SEED_PATH` | backend | no | Seed SQL path |
| `SQL_AGENT_OVERWRITE_DB` | backend | no | Rebuild database on startup |
| `SQL_AGENT_RUN_URL` | frontend | no | Backend `/run` endpoint; default route fallback is `http://localhost:8000/run` |

### Model Proxy Path
- The primary documented model path is a local OpenAI-compatible proxy at `http://localhost:4141/v1`.
- Backend startup, adapter tests, and smoke all assume the same `LLM_BASE_URL` path.
- If the proxy is not running, backend requests fail with a connection error from the model client.
- If the proxy is running but the key or route is invalid, the backend fails during model calls with an upstream auth or HTTP error.

### PostgreSQL Business-Demo Path
1. Start PostgreSQL:
   ```bash
   docker compose -f docker-compose.postgres.yml up -d postgres
   ```
2. Ensure `.env` uses:
   ```bash
   SQL_AGENT_DB_BACKEND=postgres
   SQL_AGENT_DB_URL=postgresql+psycopg://sql_agent:sql_agent@127.0.0.1:15432/sql_agent_demo
   SQL_AGENT_SCHEMA_PATH=./schema.postgres.sql
   SQL_AGENT_SEED_PATH=./seed.postgres.sql
   ```
3. Start the backend API:
   ```bash
   uv run sql-agent-api --host 127.0.0.1 --port 8000
   ```
4. Verify a READ through the CLI:
   ```bash
   uv run sql-agent "Show the inventory for all laptop products." --show-sql
   ```
5. Verify a WRITE dry-run:
   ```bash
   uv run sql-agent write "Update the inventory quantity for product LAP-001 to 15." --allow-write
   ```
6. Verify a WRITE commit:
   ```bash
   uv run sql-agent write "Update the inventory quantity for product LAP-001 to 15." --allow-write --dry-run=false
   ```

### SQLite Experiment Path
- Switch to SQLite only when you want the experiment / CLI / benchmark line:
  ```bash
  SQL_AGENT_DB_BACKEND=sqlite
  SQL_AGENT_DB_PATH=./sandbox/sandbox.db
  ```
- Run the named experiment CLI workflow:
  ```bash
  uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db
  ```
- Run the benchmark / Spider-style path:
  ```bash
  uv run python scripts/run_benchmark.py --config configs/eval/sqlite_spider.yaml --dataset datasets/spider/dev.jsonl --tag sqlite_spider
  ```
- SQLite remains out of the web demo on purpose.

### Frontend Connection
- The frontend talks to the backend through `SQL_AGENT_RUN_URL`.
- Local default:
  ```bash
  SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run pnpm --dir frontend dev --hostname 127.0.0.1 --port 3000
  ```
- If the backend is on a different host or port, only `SQL_AGENT_RUN_URL` needs to change.

### Backend HTTP Check
- Minimal request:
  ```bash
  curl -s http://127.0.0.1:8000/run \
    -H 'Content-Type: application/json' \
    -d '{"question":"Show the inventory for all laptop products.","allow_write":false,"dry_run":true}'
  ```
- READ success should return `status=SUCCESS` and a structured `result` object with `columns`, `rows`, and `row_count`.

## Troubleshooting
- `Set LLM_API_KEY to use the LLM provider.`:
  The backend started without a model key or proxy token.
- `Failed to initialize PostgreSQL backend`:
  PostgreSQL is not reachable or `SQL_AGENT_DB_URL` is wrong.
- Frontend shows adapter failure:
  Confirm `SQL_AGENT_RUN_URL` points to a live backend `/run` endpoint.
