"""SQLite sandbox initialization and query execution helpers (read + controlled write)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Sequence, Tuple

from sql_agent_demo.core.models import AgentConfig, DbExecutionError, SqlAgentError, SqlGuardViolation
from sql_agent_demo.core.safety import validate_readonly_sql, validate_write_sql


class DatabaseHandle:
    """Thin wrapper around SQLite for read + guarded write execution."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def get_table_info(self) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            tables = [row[0] for row in cursor.fetchall()]

            parts: list[str] = []
            for table in tables:
                col_cursor = conn.execute(f'PRAGMA table_info("{table}");')
                columns = [str(row[1]) for row in col_cursor.fetchall()]
                parts.append(f"{table}: {', '.join(columns)}")

        return "\n".join(parts)

    def execute_select(self, sql: str) -> Tuple[List[str], List[Sequence[object]]]:
        try:
            validate_readonly_sql(sql)
        except SqlGuardViolation as exc:
            raise DbExecutionError(sql, exc.reason) from exc

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(sql)
                columns = [desc[0] for desc in cursor.description or []]
                rows = cursor.fetchall()
                return columns, rows
        except sqlite3.Error as exc:
            raise DbExecutionError(sql, str(exc)) from exc

    def execute_write(self, sql: str, *, dry_run: bool = True, require_where: bool = True) -> Tuple[int, int | None]:
        """Execute a single INSERT/UPDATE/DELETE with guardrails.

        Returns (affected_rows, last_row_id). If dry_run is True, the change is rolled back.
        """
        try:
            validate_write_sql(sql, require_where=require_where)
        except SqlGuardViolation as exc:
            raise DbExecutionError(sql, exc.reason) from exc

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.isolation_level = None  # explicit transaction control
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute(sql)
                affected = cursor.rowcount
                last_row_id = cursor.lastrowid if hasattr(cursor, "lastrowid") else None
                if dry_run:
                    conn.execute("ROLLBACK")
                else:
                    conn.execute("COMMIT")
                return affected, last_row_id
        except sqlite3.Error as exc:
            raise DbExecutionError(sql, str(exc)) from exc


def _execute_sql_script(conn: sqlite3.Connection, script_path: Path) -> None:
    if not script_path.exists():
        raise SqlAgentError(f"SQL script not found: {script_path}")
    with script_path.open("r", encoding="utf-8") as f:
        conn.executescript(f.read())


def init_sandbox_db(config: AgentConfig) -> DatabaseHandle:
    """Initialize sandbox database based on schema and seed files."""
    db_path = Path(config.db_path)
    schema_path = Path(config.schema_path)
    seed_path = Path(config.seed_path)

    if not schema_path.exists():
        raise SqlAgentError(f"Schema file does not exist: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    needs_rebuild = config.overwrite_db or not db_path.exists()
    if needs_rebuild:
        if db_path.exists():
            db_path.unlink()
        with sqlite3.connect(db_path) as conn:
            _execute_sql_script(conn, schema_path)
            _execute_sql_script(conn, seed_path)

    return DatabaseHandle(str(db_path))


__all__ = ["DatabaseHandle", "init_sandbox_db"]
