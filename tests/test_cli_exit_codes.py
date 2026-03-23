from __future__ import annotations

from sql_agent_demo.core.models import IntentType, TaskResult, TaskStatus
from sql_agent_demo.interfaces.cli import _print_result


def test_print_result_returns_exit_code_for_unsupported(capsys) -> None:
    result = TaskResult(
        intent=IntentType.UNSUPPORTED,
        status=TaskStatus.UNSUPPORTED,
        query_result=None,
        error_message="Only read-only queries are supported.",
        raw_question="Delete all students",
        trace=[],
    )

    exit_code = _print_result(result, show_trace=False, show_sql=False)

    # Consume printed output to avoid leaking to other tests.
    capsys.readouterr()

    assert exit_code == 2
