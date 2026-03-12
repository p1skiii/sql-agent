#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_PORT="${SMOKE_BACKEND_PORT:-18080}"
DB_PATH="${SMOKE_DB_PATH:-$(mktemp -d "${TMPDIR:-/tmp}/sql-agent-smoke.XXXXXX")/smoke.db}"
DB_DIR="$(dirname "${DB_PATH}")"

cleanup() {
  rm -f "${DB_PATH}" "${DB_PATH}-shm" "${DB_PATH}-wal"
}

trap cleanup EXIT INT TERM

mkdir -p "${DB_DIR}"

export LLM_BASE_URL="${LLM_BASE_URL:-http://localhost:4141/v1}"
export LLM_API_KEY="${LLM_API_KEY:-dummy}"
export LLM_USE_SLIM="${LLM_USE_SLIM:-1}"
export SQL_AGENT_INTENT_MODEL="${SQL_AGENT_INTENT_MODEL:-gpt-4o-mini}"
export SQL_AGENT_SQL_MODEL="${SQL_AGENT_SQL_MODEL:-gpt-4o-mini}"
export SQL_AGENT_DB_PATH="${DB_PATH}"
export SQL_AGENT_SCHEMA_PATH="${REPO_ROOT}/tests/data/schema.sql"
export SQL_AGENT_SEED_PATH="${REPO_ROOT}/tests/data/seed.sql"
export SQL_AGENT_OVERWRITE_DB="true"
export SQL_AGENT_ALLOW_TRACE="true"

cd "${REPO_ROOT}"
uv run --extra openai python -m sql_agent_demo.interfaces.api --host 127.0.0.1 --port "${BACKEND_PORT}"
