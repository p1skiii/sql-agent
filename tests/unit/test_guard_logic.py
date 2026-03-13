# Tests write guard semantics with fixed SQL strings.
from __future__ import annotations

import pytest

from sql_agent_demo.core.models import SqlGuardViolation
from sql_agent_demo.core.safety import validate_write_sql

pytestmark = [pytest.mark.unit, pytest.mark.fake_model]


def test_validate_write_sql_allows_specific_update() -> None:
    validate_write_sql("UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'")


@pytest.mark.parametrize(
    "sql,reason_fragment",
    [
        ("UPDATE students SET gpa = 3.9", "WHERE clause"),
        ("DELETE FROM students WHERE 1 = 1", "tautology"),
        ("UPDATE students SET gpa = 3.9 WHERE gpa IS NOT NULL", "too broad"),
        ("DROP TABLE students", "Only INSERT/UPDATE/DELETE"),
        ("UPDATE students SET gpa = 3.9 WHERE name = 'Alice'; DELETE FROM students", "Multiple statements"),
    ],
)
def test_validate_write_sql_rejects_unsafe_shapes(sql: str, reason_fragment: str) -> None:
    with pytest.raises(SqlGuardViolation) as exc_info:
        validate_write_sql(sql, require_where=True)

    assert reason_fragment.lower() in exc_info.value.reason.lower()
