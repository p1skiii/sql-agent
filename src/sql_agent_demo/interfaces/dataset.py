"""Helpers to load structured query files for the CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Mapping


def _load_raw(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        return json.loads(text)

    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load YAML datasets.") from exc

    return yaml.safe_load(text)


def _normalize_entry(entry: Any, idx: int) -> Mapping[str, str]:
    if isinstance(entry, str):
        return {"name": f"query-{idx}", "question": entry}

    if isinstance(entry, Mapping):
        question = entry.get("question") or entry.get("q")
        if not question:
            raise ValueError(f"Entry {idx} is missing a 'question' field.")
        name = entry.get("name") or f"query-{idx}"
        return {"name": str(name), "question": str(question)}

    raise ValueError(f"Unsupported entry type at index {idx}: {type(entry)}")


def load_query_file(path_str: str) -> List[Mapping[str, str]]:
    """Load a YAML/JSON file of queries.

    Accepted shapes:
    - List of strings: ["List students", ...]
    - List of objects: [{"name": "...", "question": "..."}]
    - Object with 'queries' or 'cases' keys that map to one of the above.
    """
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    raw = _load_raw(path)
    if isinstance(raw, Mapping):
        if "queries" in raw:
            raw = raw["queries"]
        elif "cases" in raw:
            raw = raw["cases"]

    if not isinstance(raw, list):
        raise ValueError("Dataset must be a list or contain a 'queries'/'cases' list.")

    normalized = [_normalize_entry(entry, idx + 1) for idx, entry in enumerate(raw)]
    return normalized


__all__ = ["load_query_file"]
