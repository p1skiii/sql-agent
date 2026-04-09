"""YAML-backed memory and task persistence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import RunState, state_from_dict, state_to_dict


class YamlMemoryStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.sessions_dir = self.root / "sessions"
        self.db_knowledge_dir = self.root / "db_knowledge"

    def bootstrap(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.db_knowledge_dir.mkdir(parents=True, exist_ok=True)

    def load_session(self, session_id: str) -> dict[str, Any]:
        path = self.sessions_dir / f"{session_id}.yaml"
        if not path.exists():
            return {"session_id": session_id, "history": []}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"session_id": session_id, "history": []}

    def save_session(self, session_id: str, payload: dict[str, Any]) -> None:
        path = self.sessions_dir / f"{session_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def append_session_history(self, session_id: str, item: dict[str, Any]) -> None:
        payload = self.load_session(session_id)
        history = payload.get("history")
        if not isinstance(history, list):
            history = []
        history.append(item)
        payload["history"] = history[-50:]
        self.save_session(session_id, payload)

    def load_db_knowledge(self, fingerprint: str) -> dict[str, Any] | None:
        path = self.db_knowledge_dir / f"{fingerprint}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    def save_db_knowledge(self, fingerprint: str, payload: dict[str, Any]) -> None:
        path = self.db_knowledge_dir / f"{fingerprint}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


class YamlTaskStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.yaml"

    def save(self, state: RunState) -> None:
        path = self._task_path(state.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(state_to_dict(state), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def load(self, task_id: str) -> RunState | None:
        path = self._task_path(task_id)
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return state_from_dict(data)


__all__ = ["YamlMemoryStore", "YamlTaskStore"]
