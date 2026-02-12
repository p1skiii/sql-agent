# Tests read-query pipeline end-to-end for fake and real model modes.
from __future__ import annotations

from sql_agent_demo.core.models import IntentType
from sql_agent_demo.core.sql_agent import run_read_query


def test_read_query_pipeline(read_agent_ctx, model_name: str) -> None:
    question = "List all students"
    traces: list = []

    result = run_read_query(
        question=question,
        ctx=read_agent_ctx,
        intent=IntentType.READ_SIMPLE,
        traces=traces,
    )

    assert result.query_result is not None
    assert result.query_result.sql.lower().startswith("select")
    assert isinstance(result.query_result.summary, str)
    assert result.query_result.columns

    if model_name == "fake":
        assert result.query_result.rows
    else:
        assert result.query_result.rows is not None

    if read_agent_ctx.config.allow_trace:
        assert result.query_result.trace is not None
