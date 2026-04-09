"""Database adapter interfaces for orchestration runtime."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence


class DatabaseAdapter(ABC):
    backend: str

    @abstractmethod
    def introspect_schema_text(self) -> str:
        """Return compact schema text used for planning prompts."""

    @abstractmethod
    def introspect_schema_overview(self) -> list[dict[str, Any]]:
        """Return structured schema metadata for memory layer."""

    @abstractmethod
    def execute_read(self, sql: str, *, max_rows: int) -> tuple[list[str], list[Sequence[Any]]]:
        """Execute read SQL and return columns + rows."""

    @abstractmethod
    def execute_write(self, sql: str) -> int:
        """Execute write SQL and return affected rows."""

    @abstractmethod
    def estimate_write_impact(self, sql: str) -> int:
        """Estimate affected rows without persisting changes."""


class UnsupportedDatabaseBackend(RuntimeError):
    pass


__all__ = ["DatabaseAdapter", "UnsupportedDatabaseBackend"]
