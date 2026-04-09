"""Factory helpers for AMP runtime wiring."""
from __future__ import annotations

from .adapters import PostgresAdapter, UnsupportedDatabaseBackend
from .memory import YamlMemoryStore, YamlTaskStore
from .models import AgentConfig
from .orchestrator import RuntimeContext, Orchestrator, build_default_registry
from .task_service import TaskService


def build_task_service(config: AgentConfig, *, intent_model=None, sql_model=None) -> TaskService:
    if str(config.db_backend).lower() != "postgres":
        raise UnsupportedDatabaseBackend("AMP v1 supports PostgreSQL only.")

    db_adapter = PostgresAdapter(config.db_url or "")
    memory_store = YamlMemoryStore(config.memory_root)
    task_store = YamlTaskStore(config.task_root)

    ctx = RuntimeContext(
        config=config,
        db_adapter=db_adapter,
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


__all__ = ["build_task_service"]
