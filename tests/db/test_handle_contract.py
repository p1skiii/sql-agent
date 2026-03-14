# Tests the shared database handle contract across SQLite fallback and PostgreSQL.
from __future__ import annotations

from pathlib import Path

import pytest

from sql_agent_demo.core.models import AgentConfig
from sql_agent_demo.infra.db import init_sandbox_db


@pytest.mark.db
@pytest.mark.sqlite_fallback
@pytest.mark.fake_model
def test_sqlite_handle_exposes_unified_read_contract(db_handle) -> None:
    table_info = db_handle.get_table_info()
    schema_overview = db_handle.get_schema_overview()
    columns, rows = db_handle.execute_select("SELECT id, name FROM students ORDER BY id LIMIT 1")

    assert "students:" in table_info
    assert [table["name"] for table in schema_overview] == ["courses", "enrollments", "students"]
    assert schema_overview[2]["row_count"] == 6
    assert schema_overview[2]["columns"][0]["name"] == "id"
    assert columns == ["id", "name"]
    assert rows == [(1, "Alice Johnson")]


@pytest.mark.db
@pytest.mark.postgres
@pytest.mark.fake_model
def test_postgres_handle_exposes_unified_read_and_write_contract(data_dir: Path, postgres_url: str) -> None:
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

    table_info = db_handle.get_table_info()
    schema_overview = db_handle.get_schema_overview()
    columns, rows = db_handle.execute_select("SELECT sku, name FROM products ORDER BY id LIMIT 1")
    affected, last_row_id, returned_columns, returned_rows = db_handle.execute_write(
        "UPDATE inventory SET quantity = 15 WHERE product_id = 1",
        dry_run=True,
    )

    assert "products:" in table_info
    assert "inventory:" in table_info
    table_names = [table["name"] for table in schema_overview]
    assert "inventory" in table_names
    assert "products" in table_names
    assert "users" in table_names
    products_table = next(table for table in schema_overview if table["name"] == "products")
    assert products_table["columns"][0]["name"] == "id"
    assert columns == ["sku", "name"]
    assert rows == [("LAP-001", "Aurora Pro 14")]
    assert affected == 1
    assert last_row_id is None
    assert returned_columns is None
    assert returned_rows is None
