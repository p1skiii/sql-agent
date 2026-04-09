from __future__ import annotations

import pytest

from sql_agent_demo.core.models import SqlGuardViolation
from sql_agent_demo.core.safety import validate_read_sql, validate_write_sql


def test_validate_read_sql_blocks_non_select() -> None:
    with pytest.raises(SqlGuardViolation):
        validate_read_sql("UPDATE users SET name='x'")


def test_validate_read_sql_allows_single_select() -> None:
    validate_read_sql("SELECT id FROM users")


def test_validate_write_sql_requires_where_for_update_delete() -> None:
    with pytest.raises(SqlGuardViolation):
        validate_write_sql("UPDATE users SET full_name='x'")


def test_validate_write_sql_rejects_tautology() -> None:
    with pytest.raises(SqlGuardViolation):
        validate_write_sql("DELETE FROM users WHERE 1=1")
