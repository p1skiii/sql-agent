# Tests selfcheck_sql helper for disabled mode and model-driven flags.
from __future__ import annotations

import json
from typing import Any

from sql_agent_demo.core.models import SeverityLevel
from sql_agent_demo.core.sql_agent import _selfcheck_sql as selfcheck_sql


class FakeSelfCheckModel:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        _ = messages
        return self.payload


def test_selfcheck_sql_returns_info_when_disabled() -> None:
    result = selfcheck_sql("List all students", "SELECT * FROM students", model=None)

    assert result.risk_level == SeverityLevel.INFO
    assert "selfcheck" in result.notes.lower()


def test_selfcheck_sql_respects_model_block_signal() -> None:
    fake_model = FakeSelfCheckModel(
        {
            "is_readonly": False,
            "is_relevant": True,
            "risk_level": "DANGER",
            "notes": "write attempt",
        }
    )

    result = selfcheck_sql("Update students", "UPDATE students SET gpa = 4.0", model=fake_model)

    assert result.risk_level == SeverityLevel.DANGER
    assert result.is_readonly is False
    assert "write attempt" in result.notes
