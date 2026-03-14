# Test Guide

## Quick Validation
- Backend unit and Flask API contract checks:
  ```bash
  uv run pytest tests/unit tests/api --model fake
  ```

- Adapter contract checks without a live model:
  ```bash
  pnpm --dir frontend test:adapter
  ```

- Frontend contract consumption checks:
  ```bash
  pnpm --dir frontend test:frontend
  ```

## Submit-Ready Validation
- Full backend suite on the fake-model path:
  ```bash
  uv run pytest --model fake
  ```
  Covers legacy tests plus the new layered `unit`, `db`, `api`, and `integration` directories.

- Minimal real-model adapter regression:
  ```bash
  pnpm --dir frontend test:adapter:real
  ```

- Page-level frontend checks:
  ```bash
  pnpm --dir frontend test:frontend
  ```
  Verifies the UI consumes the normalized contract and does not fall back to legacy raw-only fields.

## Freeze / Release Validation
- Smoke on the default documented runtime path:
  ```bash
  pnpm --dir frontend test:smoke
  ```
  Starts the smoke backend and frontend, then validates READ, WRITE dry-run, and WRITE commit.

- Smoke on PostgreSQL:
  ```bash
  pnpm --dir frontend test:smoke:postgres
  ```
  Uses PostgreSQL through the smoke startup script and validates the same end-to-end scenarios.

## Layered Structure
- `tests/unit/`: config parsing, guard logic, serialization helpers, and other pure-module tests
- `tests/db/`: database handle contract tests for PostgreSQL and SQLite fallback
- `tests/api/`: Flask `/run`, `/api/query`, `/api/schema`, `/api/examples`, `/api/health` contract tests
- `tests/integration/`: multi-component backend integration, including PostgreSQL-backed `/run`
- `frontend/tests/*.test.ts`: adapter and helper tests
- `frontend/tests/*.spec.ts`: frontend contract consumption and browser-level validation

Legacy tests may remain in place during this phase. New tests and any critical migrated tests follow the layered structure above, but full relocation of historical tests is not required for completion.

## What Each Layer Proves
- `pytest`: backend logic, database initialization, guards, `/run` and lightweight API contract behavior, and PostgreSQL support
- `test:adapter`: fake-first `/api/chat` normalized contract invariants plus helper coverage
- `test:adapter:real`: the minimum real-model normalized regression path
- `test:frontend`: page rendering against the stable contract, including contract-consumption checks
- `test:smoke`: full browser-to-backend flow
- `test:smoke:postgres`: full browser-to-backend flow on the PostgreSQL path

## Pytest Markers
- `unit`
- `db`
- `api`
- `integration`
- `postgres`
- `sqlite_fallback`
- `real_model`
- `fake_model`

Use markers for focused local runs when needed, for example:

```bash
uv run pytest -m "unit or api" --model fake
uv run pytest -m postgres --model fake
```
