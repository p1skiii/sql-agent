from __future__ import annotations

from pathlib import Path

from sql_agent_demo.core.memory import YamlMemoryStore, YamlTaskStore
from sql_agent_demo.core.models import AgentConfig, TaskStatus
from sql_agent_demo.core.orchestrator import Orchestrator, RuntimeContext, build_default_registry
from sql_agent_demo.core.task_service import TaskService


class FakeDbAdapter:
    backend = "postgres"

    def introspect_schema_text(self) -> str:
        return "users: id, full_name"

    def introspect_schema_overview(self):
        return [{"name": "users", "row_count": 2, "columns": [{"name": "id", "type": "INTEGER"}]}]

    def execute_read(self, sql: str, *, max_rows: int):
        _ = (sql, max_rows)
        return ["id", "full_name"], [(1, "Alice"), (2, "Bob")]

    def execute_write(self, sql: str) -> int:
        if "where id = 1" in sql.lower():
            return 1
        return 3

    def estimate_write_impact(self, sql: str) -> int:
        if "where id = 1" in sql.lower():
            return 1
        return 3


class FakeIntentModel:
    def generate_json(self, messages):
        text = messages[-1]["content"].lower()
        if any(k in text for k in ("create table", "drop", "alter")):
            return {"label": "DDL"}
        if any(k in text for k in ("update", "insert", "delete")):
            return {"label": "WRITE"}
        return {"label": "READ"}


class FakeSqlModel:
    def generate_json(self, messages):
        system = messages[0]["content"].lower()
        user = messages[-1]["content"].lower()
        if "select" in system:
            return {"sql": "SELECT id, full_name FROM users ORDER BY id"}
        if "delete" in user and "all" in user:
            return {"sql": "DELETE FROM users WHERE 1=1"}
        return {"sql": "UPDATE users SET full_name = 'Alice Updated' WHERE id = 1"}


def _build_service(tmp_path: Path, *, intent_model=None, sql_model=None) -> TaskService:
    config = AgentConfig(
        db_backend="postgres",
        db_url="postgresql+psycopg://unused",
        db_target="postgres_main",
        memory_root=str(tmp_path / "memory"),
        task_root=str(tmp_path / "tasks"),
    )
    memory_store = YamlMemoryStore(config.memory_root)
    task_store = YamlTaskStore(config.task_root)
    ctx = RuntimeContext(
        config=config,
        db_adapter=FakeDbAdapter(),
        memory_store=memory_store,
        intent_model=intent_model,
        sql_model=sql_model,
    )
    service = TaskService(
        ctx=ctx,
        orchestrator=Orchestrator(build_default_registry()),
        memory_store=memory_store,
        task_store=task_store,
    )
    service.bootstrap()
    return service


def test_read_task_auto_executes_under_r0(tmp_path: Path) -> None:
    service = _build_service(tmp_path, intent_model=FakeIntentModel(), sql_model=FakeSqlModel())
    state = service.plan_task(question="List all users", session_id="s1", db_target="postgres_main")

    assert state.status == TaskStatus.SUCCEEDED
    assert state.risk_level is not None and state.risk_level.value == "R0"
    assert state.result is not None
    assert state.result["row_count"] == 2


def test_write_task_requires_confirmation_then_executes(tmp_path: Path) -> None:
    service = _build_service(tmp_path, intent_model=FakeIntentModel(), sql_model=FakeSqlModel())
    planned = service.plan_task(question="Update user 1 name", session_id="s1", db_target="postgres_main")

    assert planned.status == TaskStatus.PENDING_CONFIRMATION
    assert planned.risk_level is not None and planned.risk_level.value == "R1"

    done = service.confirm_task(task_id=planned.task_id, approve=True, comment="ok")
    assert done.status == TaskStatus.SUCCEEDED
    assert done.result is not None
    assert done.result["affected_rows"] == 1


def test_ddl_is_blocked_and_returns_proposal(tmp_path: Path) -> None:
    service = _build_service(tmp_path, intent_model=FakeIntentModel(), sql_model=FakeSqlModel())
    state = service.plan_task(question="Create table temp_x (id int)", session_id="s1", db_target="postgres_main")

    assert state.status == TaskStatus.BLOCKED
    assert state.proposal is not None
    assert state.error is not None
    assert state.error.code == "DDL_BLOCKED"


def test_model_unavailable_returns_recoverable_error(tmp_path: Path) -> None:
    service = _build_service(tmp_path, intent_model=None, sql_model=None)
    state = service.plan_task(question="List all users", session_id="s1", db_target="postgres_main")

    assert state.status == TaskStatus.FAILED
    assert state.error is not None
    assert state.error.code == "MODEL_UNAVAILABLE"
    assert state.error.recoverable is True
    assert state.result is None
