from __future__ import annotations

from pathlib import Path

from sql_agent_demo.core.memory import YamlMemoryStore


def test_session_and_db_knowledge_persistence(tmp_path: Path) -> None:
    store = YamlMemoryStore(str(tmp_path / "memory"))
    store.bootstrap()

    store.append_session_history("s1", {"task_id": "t1", "status": "PLANNED"})
    session = store.load_session("s1")
    assert session["history"][0]["task_id"] == "t1"

    store.save_db_knowledge("abc123", {"fingerprint": "abc123", "schema_text": "users: id"})
    knowledge = store.load_db_knowledge("abc123")
    assert knowledge is not None
    assert knowledge["schema_text"] == "users: id"
