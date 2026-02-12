# Tests detect_intent mapping when a model is provided and default behavior without a model.
from __future__ import annotations

from typing import Any

from sql_agent_demo.core.intent import detect_intent
from sql_agent_demo.core.models import IntentType


class FakeIntentModel:
    def __init__(self, label: str) -> None:
        self.label = label

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        _ = messages
        return {"label": self.label}


def test_detect_intent_with_model_mapping() -> None:
    model = FakeIntentModel("READ_SIMPLE")
    assert detect_intent("List students", model) == IntentType.READ_SIMPLE

    write_model = FakeIntentModel("WRITE")
    assert detect_intent("Update grades", write_model) == IntentType.WRITE


def test_detect_intent_without_model_returns_unsupported() -> None:
    assert detect_intent("List all students", None) == IntentType.UNSUPPORTED
