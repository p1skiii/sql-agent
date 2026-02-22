"""Shared JSON serialization for CLI and HTTP API."""
from __future__ import annotations

import json
from typing import Optional

from sql_agent_demo.core.models import IntentType, TaskStatus
from sql_agent_demo.core.models import StepTrace  # type: ignore


def _extract_affected(trace_steps: list[StepTrace]) -> tuple[Optional[int], Optional[bool], dict]:
    import re

    affected = None
    dry_run = None
    evidence = {}
    for step in trace_steps:
        if step.name in ("execute_write", "execute_write_probe") and step.output_preview:
            m = re.search(r"affected_rows=(\\d+)", step.output_preview)
            if m:
                affected = int(m.group(1))
            m2 = re.search(r"dry_run=(true|false)", step.output_preview, flags=re.IGNORECASE)
            if m2:
                dry_run = m2.group(1).lower() == "true"
        if step.name == "evidence" and step.output_preview:
            evidence["details"] = step.output_preview
    return affected, dry_run, evidence


def _diagnose(result) -> dict:
    msg = (result.error_message or "").lower()
    code = result.error_code or ""
    diagnosis = {"category": "UNKNOWN", "action": "inspect", "evidence": result.error_message}
    if code in ("WRITE_GUARD", "WRITE_WIDE", "WRITE_DISABLED", "WRITE_CONFIRM_REQUIRED", "WRITE_TOO_LARGE"):
        diagnosis = {"category": "GUARD", "action": "narrow_where", "evidence": result.error_message}
    elif code in ("SCHEMA_MISSING_COLUMN", "FIELDS_MISSING"):
        diagnosis = {"category": "SCHEMA_MISSING_COLUMN", "action": "adjust_columns", "evidence": result.error_message}
    elif "not null constraint" in msg or "foreign key" in msg:
        diagnosis = {"category": "DB_CONSTRAINT", "action": "add_required_fields", "evidence": result.error_message}
    elif "failed to generate" in msg or "refused" in msg or code == "WRITE_REFUSED":
        diagnosis = {"category": "LLM_SQL_INVALID", "action": "rephrase_request", "evidence": result.error_message}
    elif result.status.name == "UNSUPPORTED":
        diagnosis = {"category": "GUARD", "action": "review_policy", "evidence": result.error_message}
    elif result.status.name == "ERROR":
        diagnosis = {"category": "EXECUTION_ERROR", "action": "check_stack", "evidence": result.error_message}
    return diagnosis


def _trim_trace(trace_steps: list[StepTrace], max_steps: int = 200, max_chars: int = 20000) -> list[dict]:
    trimmed = []
    total_chars = 0
    for step in trace_steps[:max_steps]:
        preview = step.output_preview or ""
        total_chars += len(preview)
        if total_chars > max_chars:
            break
        trimmed.append(step)
    return trimmed


def result_to_json(result, show_sql: bool, flags: dict | None = None) -> dict:
    raw_trace = result.trace or (result.query_result.trace if result.query_result else None) or []
    trace_steps = _trim_trace(raw_trace)
    affected_rows, dry_run, evidence = _extract_affected(trace_steps)
    obj = {
        "ok": result.status == TaskStatus.SUCCESS,
        "mode": "WRITE" if result.intent == IntentType.WRITE else "READ",
        "question": result.raw_question,
        "status": result.status.value,
        "sql": (result.query_result.sql if result.query_result and show_sql else None),
        "summary": result.query_result.summary if result.query_result else None,
        "error_code": result.error_code if result.status != TaskStatus.SUCCESS else None,
        "reason": result.error_message,
        "hint": result.hint,
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
    if flags:
        obj["flags"] = flags
    if evidence:
        obj["evidence"] = evidence
    if result.status != TaskStatus.SUCCESS:
        obj["diagnosis"] = _diagnose(result)
    return obj


__all__ = ["result_to_json"]
