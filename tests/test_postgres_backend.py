# Tests PostgreSQL business-demo initialization, read execution, and minimal write dry-run.
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

    columns, rows = db_handle.execute_select(
        "SELECT p.sku, p.name, i.quantity FROM products p JOIN inventory i ON i.product_id = p.id ORDER BY p.id"
    )
    assert columns == ["sku", "name", "quantity"]
    assert rows[0] == ("LAP-001", "Aurora Pro 14", 12)

    affected, last_row_id, returned_columns, returned_rows = db_handle.execute_write(
        "UPDATE inventory SET quantity = 15 WHERE product_id = 1",
        dry_run=True,
    )
    assert affected == 1
    assert last_row_id is None
    assert returned_columns is None
    assert returned_rows is None

    _, verify_rows = db_handle.execute_select("SELECT quantity FROM inventory WHERE product_id = 1")
    assert verify_rows[0][0] == 12
