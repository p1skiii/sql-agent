from __future__ import annotations

from typing import Any

import pytest

from sql_agent_demo.core.factory import build_task_service
from sql_agent_demo.core.models import AgentConfig


class StubAdapter:
    def __init__(self, db_url: str) -> None:
        _ = db_url

    def introspect_schema_text(self) -> str:
        return "users: id"

    def introspect_schema_overview(self) -> list[dict[str, Any]]:
        return [{"name": "users", "row_count": 0, "columns": [{"name": "id", "type": "INTEGER"}]}]

    def execute_read(self, sql: str, *, max_rows: int):
        _ = (sql, max_rows)
        return ["id"], [(1,)]

    def execute_write(self, sql: str) -> int:
        _ = sql
        return 1

    def estimate_write_impact(self, sql: str) -> int:
        _ = sql
        return 1


class StubIntentModel:
    def generate_json(self, messages):
        _ = messages
        return {"label": "READ"}


class StubSqlModel:
    def generate_json(self, messages):
        _ = messages
        return {"sql": "SELECT id FROM users"}


def test_factory_rejects_non_postgres_backend(tmp_path) -> None:
    config = AgentConfig(db_backend="sqlite", memory_root=str(tmp_path / "m"), task_root=str(tmp_path / "t"))
    with pytest.raises(Exception):
        build_task_service(config, intent_model=StubIntentModel(), sql_model=StubSqlModel())


def test_factory_builds_service_for_postgres_with_adapter_patch(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sql_agent_demo.core.factory.PostgresAdapter", StubAdapter)
    config = AgentConfig(
        db_backend="postgres",
        db_url="postgresql://unused",
        memory_root=str(tmp_path / "m"),
        task_root=str(tmp_path / "t"),
    )
    service = build_task_service(config, intent_model=StubIntentModel(), sql_model=StubSqlModel())
    state = service.plan_task(question="List users", session_id="s1", db_target="postgres_main")

    assert state.status.value == "SUCCEEDED"
    assert state.result is not None
