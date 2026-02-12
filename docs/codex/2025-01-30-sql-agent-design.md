# Codex Session – SQL Agent Read-only Design

## Context
- Repo: langchain-sql-agent-demo (Python 3.11, uv-managed).
- MVP1 scope: read-only NL→SQL over SQLite; no HTTP/UI yet.
- Seed data: students/courses/enrollments (English-only values) via `schema.sql`/`seed.sql`.
- Tests: pytest suite with `--model fake` (deterministic fixtures) or real models; read pipeline test uses `read_agent_ctx` and explicit `IntentType.READ_SIMPLE`.
- Core architecture (per `notes/design_architecture.md`):
  - `core`: models, intent, safety, summarizer, sql_agent pipeline.
  - `infra`: config loader, db bootstrap/execute, LLM provider, logging.
  - `interfaces`: CLI shim.

## Key Decisions
- **Read-only enforcement**: `validate_readonly_sql` blocks non-SELECT, multi-statement, and dangerous keywords; executed before DB runs and after any repair.
- **JSON-first LLM IO**:
  - Intent: `generate_json` returning `{"label": ...}`; no keyword fallback; `None` model → `IntentType.UNSUPPORTED`.
  - NL→SQL: `_generate_sql_with_llm` expects `{"sql": "...", "tables": [...], "assumptions": "..."}`; refusal yields `None`.
  - Selfcheck: `_selfcheck_sql` consumes `{"pass": bool, "reason": "...", "fix_hint": "...", "risk_level": ...}` and gates execution when enabled.
  - Repair: `repair_sql` consumes `{"sql": "...", "reason": "..."}` for one-shot fixes after DB errors.
- **Schema linking**: `select_schema_subset` picks top-K relevant schema lines (keyword match) to keep prompts compact.
- **One-shot repair**: If initial execute fails, attempt a single repair, re-guard, optional second selfcheck, then retry once; otherwise return error.
- **Tracing**: Optional `StepTrace` list when `allow_trace=True` captures intent, schema load, generate, selfcheck(s), execute, summarize, repair.
- **LLM adapter**: Single `ChatOpenAI` with optional `LLM_BASE_URL`; API key read from `LLM_API_KEY` only; no fake LLM in prod code (fakes live only in tests).
- **CLI**: `sql-agent-demo` delegates to `interfaces/cli.py`; mirrors `AgentConfig` flags.
- **Selfcheck gate**: When enabled, blocks on `passed=False` before execute and after repair.
- **Testing fixtures**: `read_agent_ctx` uses `AlwaysReadIntentModel` + `FakeSqlModel` when `--model fake`; real mode builds via `build_llm_from_name` and skips if `LlmNotConfigured`.
- **README**: Comprehensive, >200 lines, documents config/env vars, prompts, flows, usage, and tests.

## Codex Dialogue (Excerpt)
- Refactored intent to JSON-based detection, removed keyword fallback.
- Added JSON-based NL→SQL generation, selfcheck gating, schema subset selection, and one-shot repair path.
- Simplified LLM provider to a single ChatOpenAI adapter with configurable base URL and unified key resolution.
- Implemented CLI wrapper and detailed README; tests not run in final step per instruction.
- Preserved test fixtures and adjusted them to use `generate_json` for intent/selfcheck expectations.

## TODO
- Run full test suite (`uv run pytest --model fake`) after dependencies/keys are in place; real-mode run when API keys available.
- Harden schema linking (beyond keyword matching) and repair prompts.
- Plan Flask API layer and trace presentation for MVP2.
- Consider richer retry/backoff and model selection policies for production use.
