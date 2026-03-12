#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_PORT="${SMOKE_BACKEND_PORT:-18080}"
DB_BACKEND="${SMOKE_DB_BACKEND:-sqlite}"
DB_PATH="${SMOKE_DB_PATH:-$(mktemp -d "${TMPDIR:-/tmp}/sql-agent-smoke.XXXXXX")/smoke.db}"
DB_DIR="$(dirname "${DB_PATH}")"
POSTGRES_PROJECT="sql-agent-smoke-${BACKEND_PORT}"
POSTGRES_PORT="${SMOKE_POSTGRES_PORT:-15432}"
POSTGRES_USER="${SQL_AGENT_POSTGRES_USER:-sql_agent}"
POSTGRES_PASSWORD="${SQL_AGENT_POSTGRES_PASSWORD:-sql_agent}"
POSTGRES_DB="${SQL_AGENT_POSTGRES_DB:-sql_agent_demo}"
POSTGRES_URL="${SMOKE_DB_URL:-postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}}"

cleanup() {
  rm -f "${DB_PATH}" "${DB_PATH}-shm" "${DB_PATH}-wal"
  if [[ "${DB_BACKEND}" == "postgres" ]]; then
    docker compose -p "${POSTGRES_PROJECT}" -f "${REPO_ROOT}/docker-compose.postgres.yml" down -v >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

mkdir -p "${DB_DIR}"

export LLM_BASE_URL="${LLM_BASE_URL:-http://localhost:4141/v1}"
export LLM_API_KEY="${LLM_API_KEY:-dummy}"
export SQL_AGENT_INTENT_MODEL="${SQL_AGENT_INTENT_MODEL:-gpt-4o-mini}"
export SQL_AGENT_SQL_MODEL="${SQL_AGENT_SQL_MODEL:-gpt-4o-mini}"
export SQL_AGENT_SCHEMA_PATH="${REPO_ROOT}/tests/data/schema.sql"
export SQL_AGENT_SEED_PATH="${REPO_ROOT}/tests/data/seed.sql"
export SQL_AGENT_OVERWRITE_DB="true"
export SQL_AGENT_ALLOW_TRACE="true"

if [[ "${DB_BACKEND}" == "postgres" ]]; then
  export SQL_AGENT_DB_BACKEND="postgres"
  export SQL_AGENT_DB_URL="${POSTGRES_URL}"
  export SQL_AGENT_POSTGRES_PORT="${POSTGRES_PORT}"
  export SQL_AGENT_POSTGRES_USER="${POSTGRES_USER}"
  export SQL_AGENT_POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
  export SQL_AGENT_POSTGRES_DB="${POSTGRES_DB}"

  docker compose -p "${POSTGRES_PROJECT}" -f "${REPO_ROOT}/docker-compose.postgres.yml" up -d postgres
  until docker compose -p "${POSTGRES_PROJECT}" -f "${REPO_ROOT}/docker-compose.postgres.yml" exec -T postgres \
    pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    sleep 1
  done
else
  export SQL_AGENT_DB_BACKEND="sqlite"
  export SQL_AGENT_DB_PATH="${DB_PATH}"
fi

cd "${REPO_ROOT}"
uv run python -m sql_agent_demo.interfaces.api --host 127.0.0.1 --port "${BACKEND_PORT}"
