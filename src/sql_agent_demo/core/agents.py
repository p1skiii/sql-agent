"""Agent implementations for AMP orchestration runtime."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Protocol

from .i18n import localize, summarize_read, summarize_write
from .models import ErrorInfo, IntentType, RiskLevel, RunState, TaskStatus, WorkflowStep
from .safety import validate_read_sql, validate_write_sql


class Agent(Protocol):
    name: str

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        ...


def _set_error(state: RunState, code: str, recoverable: bool, *, status: TaskStatus = TaskStatus.FAILED) -> RunState:
    state.error = ErrorInfo(
        code=code,
        message=localize(code, state.language, fallback=code),
        recoverable=recoverable,
    )
    state.status = status
    return state


def _extract_sql(payload: Any) -> str | None:
    if isinstance(payload, dict):
        raw = payload.get("sql")
        if raw is None:
            return None
        text = str(raw).strip()
    else:
        text = str(payload).strip()
    if not text:
        return None
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
            if text.lower().startswith("sql"):
                text = text[3:].strip()
    return text.strip()


def _map_intent(label: str) -> IntentType:
    norm = label.strip().upper()
    if norm in {"READ", "READ_QUERY", "READ_ONLY", "READ_SIMPLE", "READ_ANALYTIC"}:
        return IntentType.READ
    if norm in {"WRITE", "UPDATE", "INSERT", "DELETE", "CRUD"}:
        return IntentType.WRITE
    if norm in {"DDL", "SCHEMA_CHANGE", "ALTER", "CREATE", "DROP"}:
        return IntentType.DDL
    return IntentType.UNSUPPORTED


class IntentAgent:
    name = "intent"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        model = ctx.intent_model
        if model is None:
            return _set_error(state, "MODEL_UNAVAILABLE", True), None, "intent model missing"

        prompt = [
            {
                "role": "system",
                "content": (
                    "Classify the request into one label: READ, WRITE, DDL, UNSUPPORTED. "
                    "Return JSON: {\"label\":\"...\",\"reason\":\"...\"}."
                ),
            },
            {"role": "user", "content": state.question},
        ]

        try:
            payload = model.generate_json(prompt)
        except Exception:
            return _set_error(state, "MODEL_UNAVAILABLE", True), None, "intent model call failed"

        label = ""
        if isinstance(payload, dict):
            label = str(payload.get("label", "")).strip()
        if not label:
            label = "UNSUPPORTED"

        state.intent = _map_intent(label)
        if state.intent == IntentType.UNSUPPORTED:
            state.status = TaskStatus.BLOCKED
            _set_error(state, "UNSUPPORTED_INTENT", True, status=TaskStatus.BLOCKED)
            return state, "intent=UNSUPPORTED", None

        return state, f"intent={state.intent.value}", None


class MemoryAgent:
    name = "memory"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        session_data = ctx.memory_store.load_session(state.session_id)
        state.metadata["session_memory"] = session_data

        schema_text = ctx.db_adapter.introspect_schema_text()
        fingerprint = hashlib.sha1(schema_text.encode("utf-8")).hexdigest()
        knowledge = ctx.memory_store.load_db_knowledge(fingerprint)

        if knowledge is None:
            overview = ctx.db_adapter.introspect_schema_overview()
            knowledge = {
                "db_target": state.db_target,
                "fingerprint": fingerprint,
                "schema_text": schema_text,
                "overview": overview,
            }
            ctx.memory_store.save_db_knowledge(fingerprint, knowledge)

        state.metadata["db_fingerprint"] = fingerprint
        state.metadata["db_knowledge"] = knowledge
        return state, f"db_fingerprint={fingerprint[:8]}", None


class PlannerAgent:
    name = "planner"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        state.status = TaskStatus.PLANNED

        if state.intent == IntentType.READ:
            state.workflow = [
                WorkflowStep(step="normalize", agent="NormalizeAgent", purpose="Normalize question and language metadata."),
                WorkflowStep(step="schema", agent="SchemaAgent", purpose="Load schema context from database memory."),
                WorkflowStep(step="plan_sql", agent="SqlAgent", purpose="Generate safe read SQL."),
                WorkflowStep(step="guard", agent="GuardAgent", purpose="Apply read guard and classify risk."),
                WorkflowStep(step="execute", agent="ExecutorAgent", purpose="Execute read query if auto-executable."),
                WorkflowStep(step="summarize", agent="SummarizerAgent", purpose="Create user-facing summary."),
            ]
            state.thinking_summary = "Read task detected. The workflow will generate guarded SELECT SQL and auto-execute under R0 policy."
        elif state.intent == IntentType.WRITE:
            state.workflow = [
                WorkflowStep(step="normalize", agent="NormalizeAgent", purpose="Normalize question and language metadata."),
                WorkflowStep(step="schema", agent="SchemaAgent", purpose="Load schema context from database memory."),
                WorkflowStep(step="plan_sql", agent="SqlAgent", purpose="Generate write SQL candidate."),
                WorkflowStep(step="guard", agent="GuardAgent", purpose="Apply write guard and evaluate impact risk."),
                WorkflowStep(step="confirm", agent="OrchestratorAgent", purpose="Require user confirmation for write execution."),
                WorkflowStep(step="execute", agent="ExecutorAgent", purpose="Execute write SQL after confirmation."),
                WorkflowStep(step="summarize", agent="SummarizerAgent", purpose="Create user-facing summary."),
            ]
            state.thinking_summary = "Write task detected. The workflow will require confirmation after guard and impact analysis."
        elif state.intent == IntentType.DDL:
            state.workflow = [
                WorkflowStep(step="normalize", agent="NormalizeAgent", purpose="Normalize question and language metadata."),
                WorkflowStep(step="proposal", agent="ProposalAgent", purpose="Generate DDL proposal instead of execution."),
            ]
            state.thinking_summary = "DDL task detected. Execution is blocked by policy and will be converted to a proposal."
        else:
            _set_error(state, "UNSUPPORTED_INTENT", True, status=TaskStatus.BLOCKED)

        return state, f"workflow_steps={len(state.workflow)}", None


class NormalizeAgent:
    name = "normalize"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        normalized = re.sub(r"\s+", " ", state.question).strip()
        state.metadata["normalized_question"] = normalized
        return state, normalized[:120], None


class SchemaAgent:
    name = "schema"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        knowledge = state.metadata.get("db_knowledge")
        if not isinstance(knowledge, dict):
            return _set_error(state, "EXECUTION_FAILED", False), None, "missing db knowledge"

        schema_text = str(knowledge.get("schema_text", "")).strip()
        if not schema_text:
            schema_text = ctx.db_adapter.introspect_schema_text()

        state.metadata["schema_text"] = schema_text
        lines = len(schema_text.splitlines())
        return state, f"schema_lines={lines}", None


class SqlAgent:
    name = "plan_sql"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        if state.intent == IntentType.DDL:
            return state, "ddl task", "sql generation skipped"

        model = ctx.sql_model
        if model is None:
            return _set_error(state, "MODEL_UNAVAILABLE", True), None, "sql model missing"

        schema_text = str(state.metadata.get("schema_text", ""))
        normalized_question = str(state.metadata.get("normalized_question", state.question))

        if state.intent == IntentType.READ:
            system_prompt = (
                "You are a SQL planner. Generate exactly one PostgreSQL SELECT statement for the question. "
                "Return JSON: {\"sql\":\"...\"}."
            )
        else:
            system_prompt = (
                "You are a SQL planner. Generate exactly one PostgreSQL write statement (INSERT/UPDATE/DELETE). "
                "Return JSON: {\"sql\":\"...\"}."
            )

        user_prompt = json.dumps(
            {
                "question": normalized_question,
                "schema": schema_text,
                "intent": state.intent.value if state.intent else None,
            }
        )

        try:
            payload = model.generate_json(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception:
            return _set_error(state, "MODEL_UNAVAILABLE", True), None, "sql model call failed"

        sql = _extract_sql(payload)
        if not sql:
            return _set_error(state, "SQL_GENERATION_FAILED", True), None, "empty sql"

        state.plan_sql = sql
        return state, sql[:200], None


class GuardAgent:
    name = "guard"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        if state.intent == IntentType.DDL:
            state.risk_level = RiskLevel.R2
            state.status = TaskStatus.BLOCKED
            _set_error(state, "DDL_BLOCKED", True, status=TaskStatus.BLOCKED)
            return state, "risk=R2", "ddl blocked"

        sql = (state.plan_sql or "").strip()
        if not sql:
            return _set_error(state, "SQL_GENERATION_FAILED", True), None, "missing plan_sql"

        try:
            if state.intent == IntentType.READ:
                validate_read_sql(sql)
                state.risk_level = RiskLevel.R0
                state.status = TaskStatus.AUTO_EXECUTABLE
                return state, "risk=R0", None

            if state.intent == IntentType.WRITE:
                validate_write_sql(sql)
                impact = ctx.db_adapter.estimate_write_impact(sql)
                state.metadata["estimated_impact"] = impact
                if impact <= 1:
                    state.risk_level = RiskLevel.R1
                else:
                    state.risk_level = RiskLevel.R2
                state.status = TaskStatus.PENDING_CONFIRMATION
                return state, f"risk={state.risk_level.value},impact={impact}", None

            _set_error(state, "UNSUPPORTED_INTENT", True, status=TaskStatus.BLOCKED)
            return state, "blocked", None
        except Exception as exc:
            _set_error(state, "SQL_GUARD_BLOCKED", True)
            return state, None, str(exc)


class ProposalAgent:
    name = "proposal"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        state.proposal = {
            "title": "DDL Proposal",
            "question": state.question,
            "reason": localize("DDL_BLOCKED", state.language),
            "suggested_steps": [
                "Review schema change impact.",
                "Prepare rollback plan.",
                "Request explicit manual approval.",
            ],
        }
        state.status = TaskStatus.BLOCKED
        if state.error is None:
            _set_error(state, "DDL_BLOCKED", True, status=TaskStatus.BLOCKED)
        return state, "proposal_created", None


class ExecutorAgent:
    name = "execute"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        sql = (state.plan_sql or "").strip()
        if not sql:
            return _set_error(state, "SQL_GENERATION_FAILED", True), None, "missing sql"

        try:
            if state.intent == IntentType.READ:
                columns, rows = ctx.db_adapter.execute_read(sql, max_rows=ctx.config.max_rows)
                mapped_rows: list[dict[str, Any]] = [
                    {col: row[idx] if idx < len(row) else None for idx, col in enumerate(columns)}
                    for row in rows
                ]
                state.result = {
                    "sql": sql,
                    "columns": columns,
                    "rows": mapped_rows,
                    "row_count": len(mapped_rows),
                }
                return state, f"rows={len(mapped_rows)}", None

            if state.intent == IntentType.WRITE:
                affected = ctx.db_adapter.execute_write(sql)
                state.result = {
                    "sql": sql,
                    "affected_rows": affected,
                    "estimated_impact": state.metadata.get("estimated_impact"),
                }
                return state, f"affected={affected}", None

            return _set_error(state, "UNSUPPORTED_INTENT", True), None, "unsupported intent at execute"
        except Exception as exc:
            _set_error(state, "EXECUTION_FAILED", False)
            return state, None, str(exc)


class SummarizerAgent:
    name = "summarize"

    def run(self, state: RunState, ctx: Any) -> tuple[RunState, str | None, str | None]:
        if state.result is None:
            return _set_error(state, "EXECUTION_FAILED", False), None, "missing result"

        if state.intent == IntentType.READ:
            row_count = int(state.result.get("row_count", 0))
            state.result["summary"] = summarize_read(state.language, row_count)
        elif state.intent == IntentType.WRITE:
            affected = int(state.result.get("affected_rows", 0))
            state.result["summary"] = summarize_write(state.language, affected)
        else:
            state.result["summary"] = localize("UNSUPPORTED_INTENT", state.language)

        return state, str(state.result.get("summary", ""))[:200], None


__all__ = [
    "Agent",
    "ExecutorAgent",
    "GuardAgent",
    "IntentAgent",
    "MemoryAgent",
    "NormalizeAgent",
    "PlannerAgent",
    "ProposalAgent",
    "SchemaAgent",
    "SqlAgent",
    "SummarizerAgent",
]
