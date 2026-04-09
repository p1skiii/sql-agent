"""Core models for the AMP task orchestration runtime."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DDL = "DDL"
    UNSUPPORTED = "UNSUPPORTED"


class TaskStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PLANNED = "PLANNED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    AUTO_EXECUTABLE = "AUTO_EXECUTABLE"
    BLOCKED = "BLOCKED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class RiskLevel(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"


@dataclass
class AgentConfig:
    db_backend: str = "postgres"
    db_url: str | None = None
    db_target: str = "postgres_main"
    max_rows: int = 100
    intent_model_name: str = "gpt-4o-mini"
    sql_model_name: str = "gpt-4o-mini"
    memory_root: str = "./state/memory"
    task_root: str = "./state/tasks"


@dataclass
class WorkflowStep:
    step: str
    agent: str
    purpose: str


@dataclass
class StepTrace:
    name: str
    agent: str
    output_preview: str | None = None
    notes: str | None = None
    duration_ms: float | None = None


@dataclass
class ErrorInfo:
    code: str
    message: str
    recoverable: bool


@dataclass
class RunState:
    task_id: str
    session_id: str
    db_target: str
    question: str
    language: str
    status: TaskStatus = TaskStatus.RECEIVED
    intent: IntentType | None = None
    risk_level: RiskLevel | None = None
    thinking_summary: str = ""
    workflow: list[WorkflowStep] = field(default_factory=list)
    plan_sql: str | None = None
    result: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    trace: list[StepTrace] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class SqlGuardViolation(Exception):
    def __init__(self, sql: str, reason: str) -> None:
        super().__init__(reason)
        self.sql = sql
        self.reason = reason


def state_to_dict(state: RunState) -> dict[str, Any]:
    payload = asdict(state)
    payload["status"] = state.status.value
    payload["intent"] = state.intent.value if state.intent else None
    payload["risk_level"] = state.risk_level.value if state.risk_level else None
    return payload


def state_from_dict(payload: dict[str, Any]) -> RunState:
    workflow = [WorkflowStep(**item) for item in payload.get("workflow", [])]
    trace = [StepTrace(**item) for item in payload.get("trace", [])]
    error_data = payload.get("error")
    error = ErrorInfo(**error_data) if isinstance(error_data, dict) else None

    status_raw = payload.get("status", TaskStatus.RECEIVED.value)
    intent_raw = payload.get("intent")
    risk_raw = payload.get("risk_level")

    return RunState(
        task_id=str(payload["task_id"]),
        session_id=str(payload.get("session_id", "default")),
        db_target=str(payload.get("db_target", "postgres_main")),
        question=str(payload.get("question", "")),
        language=str(payload.get("language", "en")),
        status=TaskStatus(str(status_raw)),
        intent=IntentType(str(intent_raw)) if intent_raw else None,
        risk_level=RiskLevel(str(risk_raw)) if risk_raw else None,
        thinking_summary=str(payload.get("thinking_summary", "")),
        workflow=workflow,
        plan_sql=payload.get("plan_sql"),
        result=payload.get("result"),
        proposal=payload.get("proposal"),
        error=error,
        trace=trace,
        metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
    )


__all__ = [
    "AgentConfig",
    "ErrorInfo",
    "IntentType",
    "RiskLevel",
    "RunState",
    "SqlGuardViolation",
    "StepTrace",
    "TaskStatus",
    "WorkflowStep",
    "state_from_dict",
    "state_to_dict",
]
