"""Task orchestrator for dynamic AMP agent pool."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from .i18n import localize
from .agents import (
    Agent,
    ExecutorAgent,
    GuardAgent,
    IntentAgent,
    MemoryAgent,
    NormalizeAgent,
    PlannerAgent,
    ProposalAgent,
    SchemaAgent,
    SqlAgent,
    SummarizerAgent,
)
from .models import AgentConfig, ErrorInfo, RunState, StepTrace, TaskStatus


@dataclass
class RuntimeContext:
    config: AgentConfig
    db_adapter: Any
    memory_store: Any
    intent_model: Any | None
    sql_model: Any | None


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, key: str, agent: Agent) -> None:
        self._agents[key] = agent

    def get(self, key: str) -> Agent:
        if key not in self._agents:
            raise KeyError(f"Agent not found: {key}")
        return self._agents[key]


class Orchestrator:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def _run(self, key: str, state: RunState, ctx: RuntimeContext) -> RunState:
        agent = self.registry.get(key)
        start = time.perf_counter()
        preview = None
        notes = None
        try:
            state, preview, notes = agent.run(state, ctx)
        except Exception as exc:
            state.status = TaskStatus.FAILED
            state.error = ErrorInfo(
                code="EXECUTION_FAILED",
                message=localize("EXECUTION_FAILED", state.language),
                recoverable=False,
            )
            notes = str(exc)
        duration_ms = (time.perf_counter() - start) * 1000
        state.trace.append(
            StepTrace(
                name=key,
                agent=agent.__class__.__name__,
                output_preview=preview,
                notes=notes,
                duration_ms=duration_ms,
            )
        )
        return state

    def plan(self, state: RunState, ctx: RuntimeContext) -> RunState:
        for key in ("intent", "memory", "planner", "normalize"):
            state = self._run(key, state, ctx)
            if state.status in (TaskStatus.FAILED, TaskStatus.BLOCKED):
                return state

        if state.intent and state.intent.value == "DDL":
            state = self._run("proposal", state, ctx)
            return state

        for key in ("schema", "plan_sql", "guard"):
            state = self._run(key, state, ctx)
            if state.status == TaskStatus.FAILED:
                return state
            if state.status == TaskStatus.BLOCKED:
                return state

        if state.status == TaskStatus.AUTO_EXECUTABLE:
            state.status = TaskStatus.EXECUTING
            state = self._run("execute", state, ctx)
            if state.status == TaskStatus.FAILED:
                return state
            state = self._run("summarize", state, ctx)
            if state.status != TaskStatus.FAILED:
                state.status = TaskStatus.SUCCEEDED
            return state

        return state

    def confirm(self, state: RunState, ctx: RuntimeContext, approve: bool, comment: str | None = None) -> RunState:
        if state.status != TaskStatus.PENDING_CONFIRMATION:
            state.status = TaskStatus.FAILED
            state.error = ErrorInfo(
                code="INVALID_CONFIRMATION",
                message=localize("INVALID_CONFIRMATION", state.language),
                recoverable=True,
            )
            state.trace.append(
                StepTrace(
                    name="confirm",
                    agent="Orchestrator",
                    output_preview="confirmation rejected by state",
                    notes="task is not pending confirmation",
                )
            )
            return state

        if not approve:
            state.status = TaskStatus.BLOCKED
            state.error = ErrorInfo(
                code="USER_REJECTED",
                message=localize("USER_REJECTED", state.language),
                recoverable=True,
            )
            state.trace.append(
                StepTrace(
                    name="confirm",
                    agent="Orchestrator",
                    output_preview="rejected",
                    notes=comment or "user rejected confirmation",
                )
            )
            return state

        state.status = TaskStatus.EXECUTING
        state.trace.append(
            StepTrace(
                name="confirm",
                agent="Orchestrator",
                output_preview="approved",
                notes=comment,
            )
        )
        state = self._run("execute", state, ctx)
        if state.status == TaskStatus.FAILED:
            return state
        state = self._run("summarize", state, ctx)
        if state.status != TaskStatus.FAILED:
            state.status = TaskStatus.SUCCEEDED
        return state


def build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register("intent", IntentAgent())
    registry.register("memory", MemoryAgent())
    registry.register("planner", PlannerAgent())
    registry.register("normalize", NormalizeAgent())
    registry.register("schema", SchemaAgent())
    registry.register("plan_sql", SqlAgent())
    registry.register("guard", GuardAgent())
    registry.register("proposal", ProposalAgent())
    registry.register("execute", ExecutorAgent())
    registry.register("summarize", SummarizerAgent())
    return registry


__all__ = ["Orchestrator", "RuntimeContext", "build_default_registry"]
