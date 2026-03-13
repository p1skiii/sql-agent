"""Intent detection helpers."""
from __future__ import annotations

from typing import Any

from .models import IntentType


def _map_label_to_intent(label: str) -> IntentType:
    normalized = label.strip().upper()
    if normalized in ("READ_SIMPLE", "READ"):
        return IntentType.READ_SIMPLE
    if normalized == "READ_ANALYTIC":
        return IntentType.READ_ANALYTIC
    if normalized == "WRITE":
        return IntentType.WRITE
    if normalized == "COMPLEX_ACTION":
        return IntentType.COMPLEX_ACTION
    return IntentType.UNSUPPORTED


def detect_intent(question: str, model: Any | None) -> IntentType:
    """Detect user intent strictly via the provided model using JSON output."""
    if model is None:
        return IntentType.UNSUPPORTED

    try:
        payload = model.generate_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Classify the user's database request into one of: "
                        "READ_SIMPLE, READ_ANALYTIC, WRITE, COMPLEX_ACTION, UNSUPPORTED. "
                        "Respond ONLY with JSON: {\"label\": \"...\", \"confidence\": 0-1, \"reason\": \"...\"}."
                    ),
                },
                {"role": "user", "content": question},
            ]
        )
    except Exception:
        payload = {}

    label = payload.get("label") if isinstance(payload, dict) else None
    intent = _map_label_to_intent(str(label) if label is not None else "")
    if intent != IntentType.UNSUPPORTED:
        return intent

    # Fallback heuristic if model returns nothing
    ql = question.lower()
    if any(k in ql for k in ("insert", "update", "delete", "remove", "add", "create")):
        return IntentType.WRITE
    if any(k in ql for k in ("sum", "average", "avg", "count", "group by", "aggregate")):
        return IntentType.READ_ANALYTIC
    return IntentType.READ_SIMPLE


__all__ = ["detect_intent"]
