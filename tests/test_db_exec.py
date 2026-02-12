# Tests execute_select wrapper for read-only enforcement and error handling.
from __future__ import annotations

import pytest

from sql_agent_demo.core.models import DbExecutionError


def test_execute_select_returns_columns_and_rows(db_handle) -> None:
    columns, rows = db_handle.execute_select("SELECT id, name FROM students")

    assert columns == ["id", "name"]
    assert len(rows) >= 1


def test_execute_select_rejects_non_select(db_handle) -> None:
    with pytest.raises(DbExecutionError):
        db_handle.execute_select("UPDATE students SET gpa = 4.0")


def test_execute_select_raises_on_sql_syntax_error(db_handle) -> None:
    with pytest.raises(DbExecutionError):
        db_handle.execute_select("SELECT FROM students")
