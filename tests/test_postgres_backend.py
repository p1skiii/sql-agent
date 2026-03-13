# Tests PostgreSQL initialization, read execution, and minimal write dry-run.
from __future__ import annotations

from pathlib import Path

import pytest

from sql_agent_demo.core.models import AgentConfig
from sql_agent_demo.infra.db import init_sandbox_db

pytestmark = [pytest.mark.db, pytest.mark.postgres, pytest.mark.fake_model]


def test_postgres_read_and_minimal_write_dry_run(data_dir: Path, postgres_url: str) -> None:
    cfg = AgentConfig(
        db_backend="postgres",
        db_url=postgres_url,
        db_path="unused-for-postgres.db",
        schema_path=str(data_dir / "schema.sql"),
        seed_path=str(data_dir / "seed.sql"),
        overwrite_db=True,
        allow_write=True,
        allow_trace=True,
    )

    db_handle = init_sandbox_db(cfg)

    columns, rows = db_handle.execute_select("SELECT id, name FROM students ORDER BY id")
    assert columns == ["id", "name"]
    assert rows[0][1] == "Alice Johnson"

    affected, last_row_id, returned_columns, returned_rows = db_handle.execute_write(
        "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
        dry_run=True,
    )
    assert affected == 1
    assert last_row_id is None
    assert returned_columns is None
    assert returned_rows is None

    _, verify_rows = db_handle.execute_select("SELECT gpa FROM students WHERE name = 'Alice Johnson'")
    assert verify_rows[0][0] == pytest.approx(3.8)
