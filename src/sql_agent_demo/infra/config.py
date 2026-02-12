"""Configuration loader for the SQL agent demo."""
from __future__ import annotations

import os
from typing import Any, Dict

from sql_agent_demo.core.models import AgentConfig
from sql_agent_demo.infra.env import load_env_file


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def load_config(cli_overrides: Dict[str, Any] | None = None) -> AgentConfig:
    """Load configuration from defaults, environment variables, and CLI overrides."""
    load_env_file()
    cli_overrides = cli_overrides or {}

    env = os.environ
    defaults = AgentConfig()

    config = AgentConfig(
        top_k=_parse_int(env.get("SQL_AGENT_TOP_K"), defaults.top_k),
        max_rows=_parse_int(env.get("SQL_AGENT_MAX_ROWS"), defaults.max_rows or 0) or defaults.max_rows,
        max_summary_rows=_parse_int(env.get("SQL_AGENT_MAX_SUMMARY_ROWS"), defaults.max_summary_rows),
        max_prompt_tokens=_parse_int(env.get("SQL_AGENT_MAX_PROMPT_TOKENS"), defaults.max_prompt_tokens or 0) or None,
        max_total_tokens=_parse_int(env.get("SQL_AGENT_MAX_TOTAL_TOKENS"), defaults.max_total_tokens or 0) or None,
        max_summary_tokens=_parse_int(env.get("SQL_AGENT_MAX_SUMMARY_TOKENS"), defaults.max_summary_tokens or 0) or None,
        sql_default_limit=_parse_int(env.get("SQL_AGENT_SQL_DEFAULT_LIMIT"), defaults.sql_default_limit),
        allow_trace=_parse_bool(env.get("SQL_AGENT_ALLOW_TRACE"), defaults.allow_trace),
        db_path=env.get("SQL_AGENT_DB_PATH", defaults.db_path),
        schema_path=env.get("SQL_AGENT_SCHEMA_PATH", defaults.schema_path),
        seed_path=env.get("SQL_AGENT_SEED_PATH", defaults.seed_path),
        overwrite_db=_parse_bool(env.get("SQL_AGENT_OVERWRITE_DB"), defaults.overwrite_db),
        intent_model_name=env.get("SQL_AGENT_INTENT_MODEL", defaults.intent_model_name),
        sql_model_name=env.get("SQL_AGENT_SQL_MODEL", defaults.sql_model_name),
        selfcheck_enabled=_parse_bool(env.get("SQL_AGENT_SELFCHECK"), defaults.selfcheck_enabled),
        language=env.get("SQL_AGENT_LANGUAGE", defaults.language),
        allow_llm_summary=_parse_bool(env.get("SQL_AGENT_ALLOW_LLM_SUMMARY"), defaults.allow_llm_summary),
        allow_write=_parse_bool(env.get("SQL_AGENT_ALLOW_WRITE"), defaults.allow_write),
        require_where=_parse_bool(env.get("SQL_AGENT_REQUIRE_WHERE"), defaults.require_where),
        dry_run_default=_parse_bool(env.get("SQL_AGENT_DRY_RUN_DEFAULT"), defaults.dry_run_default),
        allow_force=_parse_bool(env.get("SQL_AGENT_ALLOW_FORCE"), defaults.allow_force),
    )

    for key, value in cli_overrides.items():
        if value is None:
            continue
        if hasattr(config, key):
            setattr(config, key, value)

    return config


__all__ = ["load_config"]
