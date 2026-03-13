# Tests stable /run result serialization for frontend consumption.
from __future__ import annotations

from sql_agent_demo.core.models import AgentContext, IntentType
from sql_agent_demo.core.sql_agent import run_read_query, run_write_query
from sql_agent_demo.interfaces.serialization import result_to_json


class FakeWriteSqlModel:
    def __init__(self, sql: str) -> None:
        self.sql = sql

    def generate_json(self, messages):  # type: ignore[no-untyped-def]
        _ = messages
        return {"sql": self.sql}


def test_result_to_json_includes_structured_read_result(read_agent_ctx) -> None:
    result = run_read_query(
        question="List the ids and names of all students.",
        ctx=read_agent_ctx,
        intent=IntentType.READ_SIMPLE,
        traces=[],
    )

    payload = result_to_json(result, show_sql=True)

    assert payload["ok"] is True
    assert payload["mode"] == "READ"
    assert payload["result"] is not None
    result_payload = payload["result"]
    assert result_payload["columns"] == ["id", "name", "city", "major", "gpa"]
    assert result_payload["row_count"] == len(result_payload["rows"])
    assert result_payload["rows"][0]["name"] == "Alice Johnson"


def test_result_to_json_includes_write_result_and_dry_run(db_config, db_handle) -> None:
    db_config.allow_write = True
    ctx = AgentContext(
        config=db_config,
        db_handle=db_handle,
        intent_model=None,
        sql_model=FakeWriteSqlModel("UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'"),
    )

    result = run_write_query(
        question="Update the student named Alice Johnson to have GPA 3.9.",
        ctx=ctx,
        intent=IntentType.WRITE,
        traces=[],
        dry_run=True,
    )
    payload = result_to_json(result, show_sql=True)

    assert payload["ok"] is True
    assert payload["mode"] == "WRITE"
    assert payload["dry_run"] is True
    assert payload["result"]["columns"] == ["id", "name", "city", "major", "gpa"]
    assert payload["result"]["row_count"] == 1
    assert payload["result"]["rows"][0]["name"] == "Alice Johnson"
    assert payload["result"]["rows"][0]["gpa"] == 3.9
