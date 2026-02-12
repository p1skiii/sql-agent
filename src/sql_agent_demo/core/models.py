"""Shared data models and exceptions for the SQL agent demo."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Sequence


class SqlAgentError(Exception):
    """Base error for SQL agent operations."""


class LlmNotConfigured(SqlAgentError):
    """Raised when an LLM provider lacks required configuration."""


class UnsupportedOperation(SqlAgentError):
    """Raised when a requested operation is not supported."""


class SqlGuardViolation(SqlAgentError):
    """Raised when SQL fails read-only safety checks."""

    def __init__(self, sql: str, reason: str) -> None:
        super().__init__(reason)
        self.sql = sql
        self.reason = reason


class DbExecutionError(SqlAgentError):
    """Raised when the database layer cannot execute a query."""

    def __init__(self, sql: str, inner_message: str) -> None:
        super().__init__(inner_message)
        self.sql = sql
        self.inner_message = inner_message


class IntentType(str, Enum):
    READ_SIMPLE = "READ_SIMPLE"
    READ_ANALYTIC = "READ_ANALYTIC"
    WRITE = "WRITE"
    COMPLEX_ACTION = "COMPLEX_ACTION"
    UNSUPPORTED = "UNSUPPORTED"


class TaskStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    UNSUPPORTED = "UNSUPPORTED"


class SeverityLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    DANGER = "DANGER"


@dataclass
class AgentConfig:
    top_k: int = 5
    max_rows: int | None = 20
    max_summary_rows: int = 50
    max_prompt_tokens: int | None = None
    max_total_tokens: int | None = None
    max_summary_tokens: int | None = None
    sql_default_limit: int = 50
    allow_trace: bool = False
    db_path: str = "./sandbox/sandbox.db"
    schema_path: str = "./schema.sql"
    seed_path: str = "./seed.sql"
    overwrite_db: bool = False
    intent_model_name: str = "gpt-4o-mini"
    sql_model_name: str = "gpt-4o-mini"
    selfcheck_enabled: bool = False
    language: str = "en"
    allow_llm_summary: bool = False
    allow_write: bool = False
    require_where: bool = True
    dry_run_default: bool = True
    allow_force: bool = False


@dataclass
class AgentContext:
    config: AgentConfig
    db_handle: Any
    intent_model: Any
    sql_model: Any


@dataclass
class StepTrace:
    name: str
    input_preview: str | None = None
    output_preview: str | None = None
    severity: SeverityLevel = SeverityLevel.INFO
    notes: str | None = None
    duration_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class QueryResult:
    sql: str
    columns: List[str]
    rows: List[Sequence[Any]]
    summary: str
    trace: List[StepTrace] | None = None


@dataclass
class TaskResult:
    intent: IntentType
    status: TaskStatus
    query_result: QueryResult | None
    error_message: str | None
    raw_question: str
    trace: List[StepTrace] | None = None


@dataclass
class SelfCheckResult:
    is_readonly: bool
    is_relevant: bool
    risk_level: SeverityLevel
    notes: str = ""
    passed: bool = True
    reason: str | None = None
    fix_hint: str | None = None
    confidence: float | None = None


__all__ = [
    "AgentConfig",
    "AgentContext",
    "DbExecutionError",
    "IntentType",
    "LlmNotConfigured",
    "QueryResult",
    "SelfCheckResult",
    "SeverityLevel",
    "SqlAgentError",
    "SqlGuardViolation",
    "StepTrace",
    "TaskResult",
    "TaskStatus",
    "UnsupportedOperation",
]
