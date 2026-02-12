"""Environment helpers for loading .env files."""
from __future__ import annotations

from pathlib import Path


def load_env_file(env_path: str | None = None) -> None:
    """Load environment variables from a .env file when present."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    path = Path(env_path) if env_path else Path(".env")
    if path.exists():
        load_dotenv(path)


__all__ = ["load_env_file"]
