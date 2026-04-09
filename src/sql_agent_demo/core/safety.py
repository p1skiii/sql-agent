"""SQL guard rules for read/write policy enforcement."""
from __future__ import annotations

import re

from .models import SqlGuardViolation


_FORBIDDEN_READ = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
)


def _has_middle_semicolon(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    return ";" in stripped


def validate_read_sql(sql: str) -> None:
    text = sql.strip()
    lower = text.lower()
    if not text:
        raise SqlGuardViolation(sql, "Empty SQL is not allowed.")
    if not lower.startswith("select"):
        raise SqlGuardViolation(sql, "Read tasks must use a SELECT statement.")
    if _has_middle_semicolon(sql):
        raise SqlGuardViolation(sql, "Multiple SQL statements are not allowed.")
    for keyword in _FORBIDDEN_READ:
        if re.search(rf"\b{keyword}\b", lower):
            raise SqlGuardViolation(sql, f"Forbidden keyword detected in read SQL: {keyword}")


def validate_write_sql(sql: str) -> None:
    text = sql.strip()
    lower = text.lower()
    if not text:
        raise SqlGuardViolation(sql, "Empty SQL is not allowed.")
    if _has_middle_semicolon(sql):
        raise SqlGuardViolation(sql, "Multiple SQL statements are not allowed.")
    if not lower.startswith(("insert", "update", "delete")):
        raise SqlGuardViolation(sql, "Write tasks only allow INSERT/UPDATE/DELETE.")
    if lower.startswith(("update", "delete")) and " where " not in f" {lower} ":
        raise SqlGuardViolation(sql, "UPDATE/DELETE statements must include WHERE.")
    if re.search(r"\bwhere\s+1\s*=\s*1\b", lower):
        raise SqlGuardViolation(sql, "WHERE clause is too broad.")


__all__ = ["validate_read_sql", "validate_write_sql"]
