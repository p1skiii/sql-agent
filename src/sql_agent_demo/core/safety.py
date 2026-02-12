"""SQL read-only guardrails."""
from __future__ import annotations

import re

from .models import SqlGuardViolation


_FORBIDDEN_KEYWORDS = ("insert", "update", "delete", "alter", "drop", "truncate", "create")


def _has_forbidden_keyword(sql: str) -> str | None:
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", sql, flags=re.IGNORECASE):
            return keyword
    return None


def validate_readonly_sql(sql: str) -> None:
    """Validate SQL is SELECT-only and free of obvious dangerous patterns."""
    normalized = sql.strip()
    lowered = normalized.lower()

    if not lowered:
        raise SqlGuardViolation(sql, "Empty SQL is not allowed.")

    if not lowered.startswith("select"):
        raise SqlGuardViolation(sql, "Only SELECT statements are allowed.")

    if ";" in lowered:
        statements = [part.strip() for part in lowered.split(";") if part.strip()]
        if len(statements) > 1:
            raise SqlGuardViolation(sql, "Multiple statements detected; only a single SELECT is allowed.")

    forbidden = _has_forbidden_keyword(lowered)
    if forbidden:
        raise SqlGuardViolation(sql, f"Forbidden keyword detected: {forbidden}")


__all__ = ["validate_readonly_sql"]
