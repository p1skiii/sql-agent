"""Shared JSON serialization for CLI and HTTP API."""
from __future__ import annotations

import json
from typing import Optional

from sql_agent_demo.core.models import IntentType, TaskStatus
from sql_agent_demo.core.models import StepTrace  # type: ignore


def _extract_affected(trace_steps: list[StepTrace]) -> tuple[Optional[int], Optional[bool]]:
    import re

    affected = None
    dry_run = None
    for step in trace_steps:
        if step.name in ("execute_write", "execute_write_probe") and step.output_preview:
            m = re.search(r"affected_rows=(\\d+)", step.output_preview)
            if m:
                affected = int(m.group(1))
            m2 = re.search(r"dry_run=(true|false)", step.output_preview, flags=re.IGNORECASE)
            if m2:
                dry_run = m2.group(1).lower() == "true"
    return affected, dry_run


def _diagnose(result) -> dict:
    msg = (result.error_message or "").lower()
    diagnosis = {"category": "UNKNOWN", "action": "inspect", "evidence": result.error_message}
    if "where clause" in msg or "wide update" in msg:
        diagnosis = {"category": "GUARD", "action": "narrow_where", "evidence": result.error_message}
    elif "not null constraint" in msg or "foreign key" in msg:
        diagnosis = {"category": "DB_CONSTRAINT", "action": "add_required_fields", "evidence": result.error_message}
    elif "failed to generate" in msg or "refused" in msg:
        diagnosis = {"category": "LLM_SQL_INVALID", "action": "rephrase_request", "evidence": result.error_message}
    elif result.status.name == "UNSUPPORTED":
        diagnosis = {"category": "GUARD", "action": "review_policy", "evidence": result.error_message}
    elif result.status.name == "ERROR":
        diagnosis = {"category": "EXECUTION_ERROR", "action": "check_stack", "evidence": result.error_message}
    return diagnosis


def result_to_json(result, show_sql: bool) -> dict:
    trace_steps = result.trace or (result.query_result.trace if result.query_result else None) or []
    affected_rows, dry_run = _extract_affected(trace_steps)
    obj = {
        "ok": result.status == TaskStatus.SUCCESS,
        "mode": "WRITE" if result.intent == IntentType.WRITE else "READ",
        "question": result.raw_question,
        "status": result.status.value,
        "sql": (result.query_result.sql if result.query_result and show_sql else None),
        "raw_sql": result.query_result.raw_sql if result.query_result else None,
        "repaired_sql": result.query_result.repaired_sql if result.query_result else None,
        "summary": result.query_result.summary if result.query_result else None,
        "error_code": result.status.value if result.status != TaskStatus.SUCCESS else None,
        "reason": result.error_message,
        "affected_rows": affected_rows,
        "dry_run": dry_run,
        "trace": [
            {
                "name": step.name,
                "duration_ms": step.duration_ms,
                "prompt_tokens": step.prompt_tokens,
                "completion_tokens": step.completion_tokens,
                "total_tokens": step.total_tokens,
                "notes": step.notes,
                "severity": step.severity.value if step.severity else None,
                "preview": step.output_preview,
            }
            for step in trace_steps
        ],
    }
    if result.status != TaskStatus.SUCCESS:
        obj["diagnosis"] = _diagnose(result)
    return obj


__all__ = ["result_to_json"]
