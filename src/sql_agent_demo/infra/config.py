"""Configuration loader for AMP runtime."""
from __future__ import annotations

import os
from typing import Any

from sql_agent_demo.core.models import AgentConfig
from sql_agent_demo.infra.env import load_env_file


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def load_config(cli_overrides: dict[str, Any] | None = None) -> AgentConfig:
    load_env_file()
    env = os.environ
    cli_overrides = cli_overrides or {}

    config = AgentConfig(
        db_backend=env.get("SQL_AGENT_DB_BACKEND", "postgres"),
        db_url=env.get("SQL_AGENT_DB_URL"),
        db_target=env.get("SQL_AGENT_DB_TARGET", "postgres_main"),
        max_rows=_parse_int(env.get("SQL_AGENT_MAX_ROWS"), 100),
        intent_model_name=env.get("SQL_AGENT_INTENT_MODEL", "gpt-4o-mini"),
        sql_model_name=env.get("SQL_AGENT_SQL_MODEL", "gpt-4o-mini"),
        memory_root=env.get("SQL_AGENT_MEMORY_ROOT", "./state/memory"),
        task_root=env.get("SQL_AGENT_TASK_ROOT", "./state/tasks"),
    )

    for key, value in cli_overrides.items():
        if value is None:
            continue
        if hasattr(config, key):
            setattr(config, key, value)

    config.db_backend = str(config.db_backend).lower()
    return config


__all__ = ["load_config"]
