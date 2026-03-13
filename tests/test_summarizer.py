# Tests summarize helper for user-friendly answers.
from __future__ import annotations

from sql_agent_demo.core.summarizer import summarize


def test_summarize_handles_no_rows() -> None:
    summary = summarize("Find students in Seattle", ["name"], [])
    assert summary == "我没有找到符合条件的结果。"


def test_summarize_with_single_column_rows() -> None:
    columns = ["name"]
    rows = [("Alice Johnson",), ("Brian Smith",)]

    summary = summarize("List all student names", columns, rows)

    assert summary.startswith("我找到了 2 个学生姓名")
    assert "Alice Johnson" in summary
    assert "Brian Smith" in summary


def test_summarize_with_multiple_columns() -> None:
    columns = ["id", "name"]
    rows = [(1, "Alice Johnson"), (2, "Brian Smith")]

    summary = summarize("List students", columns, rows)

    assert summary.startswith("我找到了 2 名学生")
    assert "Alice Johnson" in summary
    assert "Brian Smith" in summary
    assert "id" not in summary.lower()


def test_summarize_truncates_long_lists() -> None:
    columns = ["name"]
    rows = [(f"Student {i}",) for i in range(1, 13)]

    summary = summarize("List all students", columns, rows)

    assert summary.startswith("我找到了 12 名学生")
    assert "Student 1" in summary
    assert "Student 10" in summary
    assert "Student 11" not in summary
    assert "另外还有 2 个" in summary
