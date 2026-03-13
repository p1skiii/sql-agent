"""Database initialization and execution helpers for SQLite and PostgreSQL."""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Sequence, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from sql_agent_demo.core.models import AgentConfig, DbExecutionError, SqlAgentError, SqlGuardViolation
from sql_agent_demo.core.safety import validate_readonly_sql, validate_write_sql


def _resolve_sql_script_path(raw_path: str, backend: str) -> Path:
    path = Path(raw_path)
    if backend == "postgres" and path.suffix == ".sql":
        candidate = path.with_name(f"{path.stem}.postgres{path.suffix}")
        if candidate.exists():
            return candidate
    return path


def _split_sql_script(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    previous = ""

    for char in sql_text:
        if char == "'" and not in_double and previous != "\\":
            in_single = not in_single
        elif char == '"' and not in_single and previous != "\\":
            in_double = not in_double

        if char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        previous = char

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _load_sql_script(script_path: Path) -> str:
    if not script_path.exists():
        raise SqlAgentError(f"SQL script not found: {script_path}")
    return script_path.read_text(encoding="utf-8")


class DatabaseHandle(ABC):
    """Common interface for query execution across database backends."""

    def __init__(self, guard_level: str = "strict") -> None:
        self.guard_level = guard_level

    @abstractmethod
    def get_table_info(self) -> str:
        """Return lightweight schema information for prompt construction."""

    @abstractmethod
    def execute_select(self, sql: str) -> Tuple[List[str], List[Sequence[object]]]:
        """Execute a read-only query and return columns with rows."""

    @abstractmethod
    def execute_write(self, sql: str, *, dry_run: bool = True, require_where: bool = True) -> Tuple[int, int | None]:
        """Execute a guarded write and return affected rows plus optional last row id."""


class SqliteDatabaseHandle(DatabaseHandle):
    """Thin wrapper around SQLite for read + guarded write execution."""

    def __init__(self, db_path: str, guard_level: str = "strict") -> None:
        super().__init__(guard_level=guard_level)
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
            validate_readonly_sql(sql, guard_level=self.guard_level)
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
        try:
            validate_write_sql(sql, require_where=require_where, guard_level=self.guard_level)
        except SqlGuardViolation as exc:
            raise DbExecutionError(sql, exc.reason) from exc

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.isolation_level = None
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


class PostgresDatabaseHandle(DatabaseHandle):
    """Thin wrapper around PostgreSQL for read + guarded write execution."""

    def __init__(self, db_url: str, guard_level: str = "strict") -> None:
        super().__init__(guard_level=guard_level)
        self.db_url = db_url
        self.engine = create_engine(db_url, future=True, pool_pre_ping=True)

    def get_table_info(self) -> str:
        inspector = inspect(self.engine)
        tables = sorted(inspector.get_table_names(schema="public"))
        parts: list[str] = []
        for table in tables:
            columns = [str(column["name"]) for column in inspector.get_columns(table, schema="public")]
            parts.append(f"{table}: {', '.join(columns)}")
        return "\n".join(parts)

    def execute_select(self, sql: str) -> Tuple[List[str], List[Sequence[object]]]:
        try:
            validate_readonly_sql(sql, guard_level=self.guard_level)
        except SqlGuardViolation as exc:
            raise DbExecutionError(sql, exc.reason) from exc

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = [tuple(row) for row in result.fetchall()]
                return columns, rows
        except SQLAlchemyError as exc:
            raise DbExecutionError(sql, str(exc)) from exc

    def execute_write(self, sql: str, *, dry_run: bool = True, require_where: bool = True) -> Tuple[int, int | None]:
        try:
            validate_write_sql(sql, require_where=require_where, guard_level=self.guard_level)
        except SqlGuardViolation as exc:
            raise DbExecutionError(sql, exc.reason) from exc

        try:
            with self.engine.connect() as conn:
                trans = conn.begin()
                result = conn.execute(text(sql))
                affected = result.rowcount if result.rowcount and result.rowcount > 0 else 0
                if dry_run:
                    trans.rollback()
                else:
                    trans.commit()
                return affected, None
        except SQLAlchemyError as exc:
            raise DbExecutionError(sql, str(exc)) from exc


def _execute_sqlite_script(db_path: Path, schema_path: Path, seed_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_load_sql_script(schema_path))
        conn.executescript(_load_sql_script(seed_path))


def _postgres_tables_exist(engine: Engine) -> bool:
    inspector = inspect(engine)
    return bool(inspector.get_table_names(schema="public"))


def _drop_postgres_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names(schema="public"))
    if not tables:
        return
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


def _execute_engine_script(engine: Engine, script_path: Path) -> None:
    statements = _split_sql_script(_load_sql_script(script_path))
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _init_sqlite_db(config: AgentConfig) -> DatabaseHandle:
    db_path = Path(config.db_path)
    schema_path = _resolve_sql_script_path(config.schema_path, "sqlite")
    seed_path = _resolve_sql_script_path(config.seed_path, "sqlite")

    if not schema_path.exists():
        raise SqlAgentError(f"Schema file does not exist: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    needs_rebuild = config.overwrite_db or not db_path.exists()
    if needs_rebuild:
        if db_path.exists():
            db_path.unlink()
        _execute_sqlite_script(db_path, schema_path, seed_path)

    return SqliteDatabaseHandle(str(db_path), guard_level=config.guard_level)


def _init_postgres_db(config: AgentConfig) -> DatabaseHandle:
    if not config.db_url:
        raise SqlAgentError("PostgreSQL backend requires SQL_AGENT_DB_URL or --db-url.")

    schema_path = _resolve_sql_script_path(config.schema_path, "postgres")
    seed_path = _resolve_sql_script_path(config.seed_path, "postgres")
    if not schema_path.exists():
        raise SqlAgentError(f"Schema file does not exist: {schema_path}")
    if not seed_path.exists():
        raise SqlAgentError(f"Seed file does not exist: {seed_path}")

    try:
        handle = PostgresDatabaseHandle(config.db_url, guard_level=config.guard_level)
        needs_rebuild = config.overwrite_db or not _postgres_tables_exist(handle.engine)
        if needs_rebuild:
            _drop_postgres_tables(handle.engine)
            _execute_engine_script(handle.engine, schema_path)
            _execute_engine_script(handle.engine, seed_path)
        return handle
    except SQLAlchemyError as exc:
        raise SqlAgentError(f"Failed to initialize PostgreSQL backend: {exc}") from exc


def init_sandbox_db(config: AgentConfig) -> DatabaseHandle:
    """Initialize the configured database backend and return an execution handle."""
    backend = str(config.db_backend).lower()
    if backend == "postgres":
        return _init_postgres_db(config)
    if backend != "sqlite":
        raise SqlAgentError(f"Unsupported database backend: {config.db_backend}")
    return _init_sqlite_db(config)


__all__ = [
    "DatabaseHandle",
    "PostgresDatabaseHandle",
    "SqliteDatabaseHandle",
    "init_sandbox_db",
]
