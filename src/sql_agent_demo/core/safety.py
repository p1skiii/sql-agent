"""SQL read-only guardrails."""
from __future__ import annotations

import re

from .models import SqlGuardViolation


_FORBIDDEN_KEYWORDS = ("insert", "update", "delete", "alter", "drop", "truncate", "create")
_WRITE_FORBIDDEN = ("alter", "drop", "truncate", "create", "grant", "revoke", "vacuum", "reindex")
_WRITE_ALLOWED_PREFIXES = ("insert", "update", "delete")


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


def _has_middle_semicolon(text: str) -> bool:
    """Return True if a semicolon appears before the end (indicating multiple statements)."""
    stripped = text.rstrip()
    if ";" not in stripped:
        return False
    # Allow a single trailing semicolon.
    core = stripped[:-1] if stripped.endswith(";") else stripped
    return ";" in core


def validate_write_sql(sql: str, require_where: bool = True) -> None:
    """Validate SQL is a single-statement INSERT/UPDATE/DELETE with safe shape."""
    normalized = sql.strip()
    lowered = normalized.lower()

    if not lowered:
        raise SqlGuardViolation(sql, "Empty SQL is not allowed.")

    if _has_middle_semicolon(lowered):
        raise SqlGuardViolation(sql, "Multiple statements detected; only one write statement is allowed.")

    if not lowered.startswith(_WRITE_ALLOWED_PREFIXES):
        raise SqlGuardViolation(sql, "Only INSERT/UPDATE/DELETE statements are allowed for writes.")

    if any(re.search(rf"\b{kw}\b", lowered, flags=re.IGNORECASE) for kw in _WRITE_FORBIDDEN):
        raise SqlGuardViolation(sql, "Forbidden keyword detected in write SQL.")

    needs_where = require_where and (lowered.startswith("update") or lowered.startswith("delete"))
    if needs_where:
        if " where " not in f" {lowered} ":
            raise SqlGuardViolation(sql, "UPDATE/DELETE must include a WHERE clause.")
        if re.search(r"\bwhere\s+1\s*=\s*1\b", lowered, flags=re.IGNORECASE):
            raise SqlGuardViolation(sql, "WHERE clause is too broad (tautology detected).")

    table_match = re.match(r"\s*(insert\s+into|update|delete\s+from)\s+([a-zA-Z_][\\w]*)", lowered, flags=re.IGNORECASE)
    if not table_match:
        raise SqlGuardViolation(sql, "Unable to identify target table in write SQL.")


__all__ = ["validate_readonly_sql", "validate_write_sql"]
