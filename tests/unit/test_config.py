# Tests configuration parsing and normalization without loading external services.
from __future__ import annotations

import pytest

from sql_agent_demo.infra import config as config_module

pytestmark = [pytest.mark.unit, pytest.mark.fake_model]


def test_load_config_parses_postgres_env_and_normalizes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "load_env_file", lambda: None)
    monkeypatch.setenv("SQL_AGENT_DB_BACKEND", "POSTGRES")
    monkeypatch.setenv("SQL_AGENT_DB_URL", "postgresql+psycopg://demo:demo@127.0.0.1:15432/demo")
    monkeypatch.setenv("SQL_AGENT_ALLOW_WRITE", "yes")
    monkeypatch.setenv("SQL_AGENT_DRY_RUN_DEFAULT", "false")
    monkeypatch.setenv("SQL_AGENT_GUARD_LEVEL", "LENIENT")

    cfg = config_module.load_config()

    assert cfg.db_backend == "postgres"
    assert cfg.db_url == "postgresql+psycopg://demo:demo@127.0.0.1:15432/demo"
    assert cfg.allow_write is True
    assert cfg.dry_run_default is False
    assert cfg.guard_level == "loose"


def test_load_config_prefers_cli_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "load_env_file", lambda: None)
    monkeypatch.setenv("SQL_AGENT_DB_BACKEND", "postgres")
    monkeypatch.setenv("SQL_AGENT_DB_PATH", "/tmp/env.db")
    monkeypatch.setenv("SQL_AGENT_ALLOW_TRACE", "false")

    cfg = config_module.load_config(
        {
            "db_backend": "sqlite",
            "db_path": "/tmp/cli.db",
            "allow_trace": True,
        }
    )

    assert cfg.db_backend == "sqlite"
    assert cfg.db_path == "/tmp/cli.db"
    assert cfg.allow_trace is True


def test_load_config_defaults_to_sqlite_when_db_env_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "load_env_file", lambda: None)
    monkeypatch.delenv("SQL_AGENT_DB_BACKEND", raising=False)
    monkeypatch.delenv("SQL_AGENT_DB_URL", raising=False)
    monkeypatch.delenv("SQL_AGENT_DB_PATH", raising=False)

    cfg = config_module.load_config()

    assert cfg.db_backend == "sqlite"
    assert cfg.db_url is None
    assert cfg.db_path.endswith("sandbox.db")
