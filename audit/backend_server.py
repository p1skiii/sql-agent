"""Audit backend server with deterministic fake models for response sampling."""
from __future__ import annotations

import argparse
import re
from typing import Any

import sql_agent_demo.interfaces.api as api_module


READ_SUCCESS_QUESTION = "Audit sample: list student ids and names"
WRITE_DRY_RUN_QUESTION = "Audit sample: dry-run update Alice Johnson GPA to 3.9"
WRITE_COMMIT_QUESTION = "Audit sample: commit update Alice Johnson GPA to 3.9"
UNSUPPORTED_QUESTION = "Audit sample: unsupported write when writes are disabled"
ERROR_QUESTION = "Audit sample: error write with an invalid column"
VERIFICATION_READ_QUESTION = "Audit sample: verify Alice Johnson GPA after commit"


QUESTION_TO_INTENT = {
    READ_SUCCESS_QUESTION: "READ_SIMPLE",
    WRITE_DRY_RUN_QUESTION: "WRITE",
    WRITE_COMMIT_QUESTION: "WRITE",
    UNSUPPORTED_QUESTION: "WRITE",
    ERROR_QUESTION: "WRITE",
    VERIFICATION_READ_QUESTION: "READ_SIMPLE",
}

QUESTION_TO_SQL = {
    READ_SUCCESS_QUESTION: "SELECT id, name FROM students",
    WRITE_DRY_RUN_QUESTION: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
    WRITE_COMMIT_QUESTION: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
    UNSUPPORTED_QUESTION: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
    ERROR_QUESTION: "UPDATE students SET missing_col = 3.9 WHERE name = 'Alice Johnson'",
    VERIFICATION_READ_QUESTION: "SELECT gpa FROM students WHERE name = 'Alice Johnson'",
}


def _extract_question(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""

    user_content = str(messages[-1].get("content", ""))
    match = re.search(r"Question:\s*(.*?)\s*Return only JSON\.", user_content, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return user_content.strip()


class AuditIntentModel:
    """Return deterministic intent labels for known audit questions."""

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        question = str(messages[-1].get("content", "")).strip() if messages else ""
        return {"label": QUESTION_TO_INTENT.get(question, "READ_SIMPLE")}


class AuditSqlModel:
    """Return deterministic SQL for known audit questions."""

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        question = _extract_question(messages)
        sql = QUESTION_TO_SQL.get(question)
        return {"sql": sql} if sql else {}


def _patch_models() -> None:
    api_module.build_models = lambda config: (AuditIntentModel(), AuditSqlModel())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the audit backend server with fake models.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--schema-path", required=True)
    parser.add_argument("--seed-path", required=True)
    parser.add_argument("--max-rows", type=int, default=10)
    args = parser.parse_args()

    _patch_models()

    app = api_module.create_app(
        {
            "db_path": args.db_path,
            "schema_path": args.schema_path,
            "seed_path": args.seed_path,
            "overwrite_db": True,
            "allow_trace": True,
            "max_rows": args.max_rows,
        }
    )
    app.run(host=args.host, port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()
