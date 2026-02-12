# Tests SQL guard rules for read-only enforcement.
from __future__ import annotations

import pytest

from sql_agent_demo.core.models import SqlGuardViolation
from sql_agent_demo.core.safety import validate_readonly_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM students",
        "  SELECT id, name FROM students;  ",
    ],
)
def test_validate_readonly_sql_allows_select(sql: str) -> None:
    validate_readonly_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE students SET gpa = 4.0",
        "DELETE FROM students",
        "INSERT INTO students VALUES (1, 'X', 'Y', 'Z', 3.0)",
        "SELECT 1; SELECT 2",
        "SELECT * FROM students; DROP TABLE students",
        "TRUNCATE TABLE students",
        "CREATE TABLE tmp (id INT)",
        "",
        "   ",
    ],
)
def test_validate_readonly_sql_blocks_writes(sql: str) -> None:
    with pytest.raises(SqlGuardViolation):
        validate_readonly_sql(sql)
