# SQL Agent

Read/write-guarded NL to SQL over PostgreSQL or SQLite, with a Flask backend and a Next.js frontend.

- PostgreSQL is the business-demo database for the web app, integration flow, and defense/demo screenshots.
- SQLite is the experiment database for CLI validation, Spider-style runs, benchmark scripts, and low-cost debugging.

## Recommended Entry Points
- Business demo CLI: `uv run sql-agent "Show the inventory for all laptop products." --show-sql`
- API: `uv run sql-agent-api --host 127.0.0.1 --port 8000`
- SQLite experiment CLI: `uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db`

Legacy compatibility:
- `uv run sql-agent-demo ...` still works, but it is no longer the primary documented entry.

## Where To Start
- Runtime setup and startup flow: [docs/run_guide.md](/Users/wang/i/langchain-sql/docs/run_guide.md)
- Test and smoke commands: [docs/test_guide.md](/Users/wang/i/langchain-sql/docs/test_guide.md)
- Frontend normalized contract: [frontend/adapter_contract.md](/Users/wang/i/langchain-sql/frontend/adapter_contract.md)

## Runtime Notes
- Use `.env.example` as the minimum runtime template.
- The default documented model proxy path is `http://localhost:4141/v1`.
- The frontend connects to the backend through `SQL_AGENT_RUN_URL`.
