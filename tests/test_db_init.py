# Tests init_sandbox_db overwrite behavior and basic seeding guarantees.
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sql_agent_demo.core.models import AgentConfig, SqlAgentError
from sql_agent_demo.infra.db import init_sandbox_db


def _make_config(tmp_path: Path, data_dir: Path, overwrite_db: bool = True) -> AgentConfig:
    return AgentConfig(
        top_k=5,
        max_rows=10,
        allow_trace=True,
        db_path=str(tmp_path / "sandbox.db"),
        schema_path=str(data_dir / "schema.sql"),
        seed_path=str(data_dir / "seed.sql"),
        overwrite_db=overwrite_db,
        intent_model_name="fake-intent",
        sql_model_name="fake-sql",
        selfcheck_enabled=False,
        language="en",
    )


def test_init_creates_db_with_seed(tmp_path: Path, data_dir: Path) -> None:
    cfg = _make_config(tmp_path, data_dir, overwrite_db=True)
    db_handle = init_sandbox_db(cfg)

    columns, rows = db_handle.execute_select("SELECT COUNT(*) FROM students")
    assert columns == ["COUNT(*)"]
    assert rows and rows[0][0] > 0

    _, names = db_handle.execute_select("SELECT name FROM students")
    seeded_names = {row[0] for row in names}
    assert "Alice Johnson" in seeded_names


def test_init_respects_overwrite_false(tmp_path: Path, data_dir: Path) -> None:
    cfg = _make_config(tmp_path, data_dir, overwrite_db=True)
    init_sandbox_db(cfg)

    with sqlite3.connect(cfg.db_path) as conn:
        conn.execute('INSERT INTO students (name, city, major, gpa) VALUES ("Noise Student", "Nowhere", "Noise", 3.0)')
        conn.commit()

    cfg.overwrite_db = False
    db_handle = init_sandbox_db(cfg)

    _, rows = db_handle.execute_select('SELECT name FROM students WHERE name = "Noise Student"')
    assert rows, "Noise row should survive when overwrite_db is False"


def test_init_rebuilds_when_overwrite_true(tmp_path: Path, data_dir: Path) -> None:
    cfg = _make_config(tmp_path, data_dir, overwrite_db=True)
    init_sandbox_db(cfg)

    with sqlite3.connect(cfg.db_path) as conn:
        conn.execute('INSERT INTO students (name, city, major, gpa) VALUES ("Ephemeral", "Nowhere", "Noise", 2.5)')
        conn.commit()

    cfg.overwrite_db = True
    db_handle = init_sandbox_db(cfg)

    _, rows = db_handle.execute_select('SELECT name FROM students WHERE name = "Ephemeral"')
    assert not rows, "Noise row should be removed after rebuild"

    _, count_rows = db_handle.execute_select("SELECT COUNT(*) FROM students")
    assert count_rows and count_rows[0][0] == 6


def test_init_raises_for_missing_schema(tmp_path: Path, data_dir: Path) -> None:
    cfg = _make_config(tmp_path, data_dir, overwrite_db=True)
    cfg.schema_path = str(Path(cfg.schema_path).with_name("missing_schema.sql"))

    with pytest.raises(SqlAgentError):
        init_sandbox_db(cfg)
