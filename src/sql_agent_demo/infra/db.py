"""Database adapter bootstrap for AMP runtime."""
from __future__ import annotations

from sql_agent_demo.core.adapters import DatabaseAdapter, PostgresAdapter, UnsupportedDatabaseBackend
from sql_agent_demo.core.models import AgentConfig


def build_database_adapter(config: AgentConfig) -> DatabaseAdapter:
    backend = str(config.db_backend).lower()
    if backend == "postgres":
        return PostgresAdapter(config.db_url or "")
    raise UnsupportedDatabaseBackend(
        f"AMP v1 currently supports PostgreSQL only; received backend={backend!r}."
    )


__all__ = ["build_database_adapter"]
