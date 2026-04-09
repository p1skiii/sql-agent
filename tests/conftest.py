from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sql_agent_demo.core.memory import YamlMemoryStore, YamlTaskStore
from sql_agent_demo.core.models import AgentConfig
from sql_agent_demo.core.orchestrator import Orchestrator, RuntimeContext, build_default_registry
from sql_agent_demo.core.task_service import TaskService
from sql_agent_demo.interfaces.api import create_app


class FakeDbAdapter:
    backend = "postgres"

    def introspect_schema_text(self) -> str:
        return "users: id, full_name, email"

    def introspect_schema_overview(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "users",
                "row_count": 2,
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "full_name", "type": "TEXT"},
                    {"name": "email", "type": "TEXT"},
                ],
            }
        ]

    def execute_read(self, sql: str, *, max_rows: int) -> tuple[list[str], list[tuple[Any, ...]]]:
        _ = (sql, max_rows)
        return ["id", "full_name"], [(1, "Alice"), (2, "Bob")]

    def execute_write(self, sql: str) -> int:
        if "where id = 1" in sql.lower():
            return 1
        return 3

    def estimate_write_impact(self, sql: str) -> int:
        q = sql.lower()
        if "where id = 1" in q:
            return 1
        return 3


class FakeIntentModel:
    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        text = messages[-1]["content"].lower()
        if any(k in text for k in ("create table", "drop", "alter")):
            return {"label": "DDL"}
        if any(k in text for k in ("update", "insert", "delete")):
            return {"label": "WRITE"}
        if any(k in text for k in ("list", "show", "find", "select")):
            return {"label": "READ"}
        return {"label": "UNSUPPORTED"}


class FakeSqlModel:
    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        system = messages[0]["content"].lower()
        user = messages[-1]["content"]
        try:
            payload = json.loads(user)
            question = str(payload.get("question", "")).lower()
        except Exception:
            question = user.lower()

        if "select" in system:
            return {"sql": "SELECT id, full_name FROM users ORDER BY id"}

        if "delete" in question and "all" in question:
            return {"sql": "DELETE FROM users WHERE 1=1"}

        return {"sql": "UPDATE users SET full_name = 'Alice Updated' WHERE id = 1"}


@pytest.fixture
def task_service(tmp_path: Path) -> TaskService:
    config = AgentConfig(
        db_backend="postgres",
        db_url="postgresql+psycopg://unused",
        db_target="postgres_main",
        memory_root=str(tmp_path / "memory"),
        task_root=str(tmp_path / "tasks"),
        max_rows=50,
    )
    memory_store = YamlMemoryStore(config.memory_root)
    task_store = YamlTaskStore(config.task_root)
    ctx = RuntimeContext(
        config=config,
        db_adapter=FakeDbAdapter(),
        memory_store=memory_store,
        intent_model=FakeIntentModel(),
        sql_model=FakeSqlModel(),
    )
    service = TaskService(
        ctx=ctx,
        orchestrator=Orchestrator(build_default_registry()),
        memory_store=memory_store,
        task_store=task_store,
    )
    service.bootstrap()
    return service


@pytest.fixture
def api_client(task_service: TaskService):
    app = create_app(service=task_service, config=task_service.ctx.config)
    app.testing = True
    return app.test_client()
