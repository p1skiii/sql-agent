"""Serialization helpers for AMP task responses."""
from __future__ import annotations

from typing import Any

from sql_agent_demo.core.models import RunState, TaskStatus


def state_to_response(state: RunState) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_id": state.task_id,
        "status": state.status.value,
        "risk_level": state.risk_level.value if state.risk_level else None,
        "thinking_summary": state.thinking_summary,
        "workflow": [
            {"step": item.step, "agent": item.agent, "purpose": item.purpose}
            for item in state.workflow
        ],
        "result": state.result,
        "proposal": state.proposal,
        "error": (
            {
                "code": state.error.code,
                "message": state.error.message,
                "recoverable": state.error.recoverable,
            }
            if state.error
            else None
        ),
        "trace": [
            {
                "name": step.name,
                "agent": step.agent,
                "preview": step.output_preview,
                "notes": step.notes,
                "duration_ms": step.duration_ms,
            }
            for step in state.trace
        ],
    }
    return payload


def status_code_for_state(state: RunState) -> int:
    if state.status == TaskStatus.FAILED:
        if state.error and state.error.code == "TASK_NOT_FOUND":
            return 404
        if state.error and state.error.code == "MODEL_UNAVAILABLE":
            return 503
        return 500
    if state.status == TaskStatus.BLOCKED:
        return 409
    return 200


__all__ = ["state_to_response", "status_code_for_state"]
