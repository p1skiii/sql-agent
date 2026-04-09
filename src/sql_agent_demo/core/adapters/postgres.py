"""PostgreSQL adapter for AMP orchestration runtime."""
from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .base import DatabaseAdapter


class PostgresAdapter(DatabaseAdapter):
    backend = "postgres"

    def __init__(self, db_url: str) -> None:
        if not db_url:
            raise RuntimeError("PostgreSQL db_url is required.")
        self.db_url = db_url
        self.engine: Engine = create_engine(db_url, future=True, pool_pre_ping=True)

    def introspect_schema_text(self) -> str:
        inspector = inspect(self.engine)
        lines: list[str] = []
        for table in sorted(inspector.get_table_names(schema="public")):
            cols = [str(col["name"]) for col in inspector.get_columns(table, schema="public")]
            lines.append(f"{table}: {', '.join(cols)}")
        return "\n".join(lines)

    def introspect_schema_overview(self) -> list[dict[str, Any]]:
        inspector = inspect(self.engine)
        tables = sorted(inspector.get_table_names(schema="public"))
        overview: list[dict[str, Any]] = []
        with self.engine.connect() as conn:
            for table in tables:
                cols = [
                    {"name": str(col["name"]), "type": str(col["type"])}
                    for col in inspector.get_columns(table, schema="public")
                ]
                row_count = int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
                overview.append({"name": table, "row_count": row_count, "columns": cols})
        return overview

    def execute_read(self, sql: str, *, max_rows: int) -> tuple[list[str], list[Sequence[Any]]]:
        final_sql = sql.strip().rstrip(";")
        if " limit " not in final_sql.lower() and max_rows > 0:
            final_sql = f"{final_sql} LIMIT {max_rows}"
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(final_sql))
                columns = list(result.keys())
                rows = [tuple(row) for row in result.fetchall()]
                return columns, rows
        except SQLAlchemyError as exc:
            raise RuntimeError(str(exc)) from exc

    def execute_write(self, sql: str) -> int:
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text(sql))
                return max(int(result.rowcount or 0), 0)
        except SQLAlchemyError as exc:
            raise RuntimeError(str(exc)) from exc

    def estimate_write_impact(self, sql: str) -> int:
        try:
            with self.engine.connect() as conn:
                trans = conn.begin()
                try:
                    result = conn.execute(text(sql))
                    affected = max(int(result.rowcount or 0), 0)
                finally:
                    trans.rollback()
            return affected
        except SQLAlchemyError as exc:
            raise RuntimeError(str(exc)) from exc


__all__ = ["PostgresAdapter"]
