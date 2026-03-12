# Tests serialization helpers that feed the stable /run contract.
from __future__ import annotations

import pytest

from sql_agent_demo.core.models import IntentType, QueryResult, SeverityLevel, StepTrace, TaskResult, TaskStatus
from sql_agent_demo.interfaces.serialization import result_to_json

pytestmark = [pytest.mark.unit, pytest.mark.fake_model]


def test_result_to_json_serializes_rows_as_objects_and_extracts_write_flags() -> None:
    trace = [
        StepTrace(name="execute_write_probe", output_preview="affected_rows=2, dry_run=True"),
        StepTrace(name="execute_write", output_preview="affected_rows=1, dry_run=False", severity=SeverityLevel.INFO),
    ]
    result = TaskResult(
        intent=IntentType.WRITE,
        status=TaskStatus.SUCCESS,
        query_result=QueryResult(
            sql="UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
            columns=["id", "name"],
            rows=[(1, "Alice Johnson")],
            row_count=1,
            summary="Updated 1 row(s)",
            trace=trace,
        ),
        error_message=None,
        raw_question="Update Alice Johnson to 3.9",
        trace=trace,
    )

    payload = result_to_json(result, show_sql=True)

    assert payload["ok"] is True
    assert payload["mode"] == "WRITE"
    assert payload["affected_rows"] == 1
    assert payload["dry_run"] is False
    assert payload["result"] == {
        "columns": ["id", "name"],
        "rows": [{"id": 1, "name": "Alice Johnson"}],
        "row_count": 1,
    }


def test_result_to_json_adds_diagnosis_for_unsupported_and_error_statuses() -> None:
    unsupported = TaskResult(
        intent=IntentType.WRITE,
        status=TaskStatus.UNSUPPORTED,
        query_result=None,
        error_message="Write operations are disabled. Use --allow-write to enable.",
        raw_question="Update Alice Johnson to 3.9",
        trace=[StepTrace(name="intent_detection", output_preview="WRITE")],
    )
    error = TaskResult(
        intent=IntentType.READ_SIMPLE,
        status=TaskStatus.ERROR,
        query_result=None,
        error_message="no such column: missing_col",
        raw_question="Show missing_col",
        trace=[StepTrace(name="execute_sql", output_preview="row_count=0")],
    )

    unsupported_payload = result_to_json(unsupported, show_sql=True)
    error_payload = result_to_json(error, show_sql=True)

    assert unsupported_payload["diagnosis"]["category"] == "GUARD"
    assert error_payload["diagnosis"]["category"] == "EXECUTION_ERROR"
