# LangChain SQL Agent Demo – Read/Write (guarded) NL→SQL

Turn English questions into safe, primarily read-only SQL over a SQLite sandbox. Backend-only (Python 3.11) with a CLI and Python API; writes are opt-in and guarded.

## Quickstart
1) Install deps: `uv sync`
2) Prepare env:
   ```bash
   cp .env.example .env
   # edit .env with at least
   LLM_API_KEY=sk-your-key
   LLM_BASE_URL=https://api.openai.com/v1  # or your gateway
   SQL_AGENT_INTENT_MODEL=gpt-4o-mini
   SQL_AGENT_SQL_MODEL=gpt-4o-mini
   ```
3) Real query: `uv run sql-agent-demo "List all students" --trace --selfcheck`

## Configuration
- `.env` is auto-loaded; env vars override defaults.
- Required: `LLM_API_KEY`; optional: `LLM_BASE_URL`.
- Models: `SQL_AGENT_INTENT_MODEL`, `SQL_AGENT_SQL_MODEL` (defaults: `gpt-4o-mini`).
- DB/toggles (defaults in `AgentConfig`): `SQL_AGENT_DB_PATH`, `SQL_AGENT_SCHEMA_PATH`, `SQL_AGENT_SEED_PATH`, `SQL_AGENT_OVERWRITE_DB`, `SQL_AGENT_TOP_K`, `SQL_AGENT_MAX_ROWS`, `SQL_AGENT_ALLOW_TRACE`, `SQL_AGENT_SELFCHECK`, `SQL_AGENT_LANGUAGE` (en).
- Budgets (optional): `SQL_AGENT_MAX_PROMPT_TOKENS`, `SQL_AGENT_MAX_TOTAL_TOKENS`, `SQL_AGENT_MAX_SUMMARY_ROWS`, `SQL_AGENT_MAX_SUMMARY_TOKENS`, `SQL_AGENT_ALLOW_LLM_SUMMARY` (default False).

## Usage
- CLI (single): `uv run sql-agent-demo "Which courses have 4 credits?" --trace --show-sql`
- CLI (file, first query only by default): `uv run sql-agent-demo run-file datasets/sample.yaml --limit 1 --trace`
- CLI (guarded write, dry-run by default): `uv run sql-agent-demo write "Update students set gpa = 3.8 where name = 'Alice Johnson'" --allow-write`
- Commit a write (skip dry-run): `uv run sql-agent-demo write "Update students set gpa = 3.6 where name = 'Alice Johnson'" --allow-write --dry-run=false`
- Python:
  ```python
  from sql_agent_demo.infra.config import load_config
  from sql_agent_demo.infra.db import init_sandbox_db
  from sql_agent_demo.infra.llm_provider import build_models
  from sql_agent_demo.core.models import AgentContext
  from sql_agent_demo.core.sql_agent import run_task

  cfg = load_config({"allow_trace": True})
  db = init_sandbox_db(cfg)
  intent_model, sql_model = build_models(cfg)
  ctx = AgentContext(config=cfg, db_handle=db, intent_model=intent_model, sql_model=sql_model)
  result = run_task("List students with GPA > 3.5", ctx)
  print(result.status, result.query_result.summary if result.query_result else result.error_message)
  ```

## Tests
- Fake mode (deterministic, no API): `uv run pytest --model fake`
- Real model (uses `.env` automatically): `uv run pytest --model kimi-k2-0711-preview`

## More details
- Read-only guardrails block non-SELECT and multi-statement SQL.
- Sandbox DB is built from `schema.sql` + `seed.sql`; `init_sandbox_db` can rebuild with `overwrite_db`.
- Core pipeline: `src/sql_agent_demo/core/sql_agent.py`; CLI: `src/sql_agent_demo/interfaces/cli.py`; config/env: `src/sql_agent_demo/infra`.
