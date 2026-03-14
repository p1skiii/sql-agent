"""Thin Flask API exposing the same JSON schema as the CLI."""
from __future__ import annotations

import argparse
from dataclasses import replace
from typing import Any

from flask import Flask, jsonify, request

from sql_agent_demo.core.models import AgentContext, SqlGuardViolation, TaskStatus
from sql_agent_demo.core.sql_agent import run_task
from sql_agent_demo.infra.config import load_config
from sql_agent_demo.infra.db import DatabaseHandle, init_sandbox_db
from sql_agent_demo.infra.env import load_env_file
from sql_agent_demo.infra.llm_provider import build_models
from sql_agent_demo.infra.logging import setup_logging
from sql_agent_demo.interfaces.serialization import result_to_json


EXAMPLE_QUERIES = [
    {"id": "students-list", "question": "List the ids and names of all students."},
    {"id": "cs-students", "question": "Find all students majoring in Computer Science."},
    {"id": "course-credits", "question": "Show the course code and credits for all courses."},
    {"id": "high-gpa", "question": "Which students have a GPA above 3.7?"},
    {"id": "enrollment-grades", "question": "Show the student names and grades for course CS205."},
]


def _build_agent_context(
    *,
    config: Any,
    db_handle: DatabaseHandle,
    intent_model: Any,
    sql_model: Any,
    payload: dict[str, Any],
) -> tuple[AgentContext, Any]:
    overrides = {}
    for key, field in (("allow_write", "allow_write"), ("dry_run", "dry_run_default"), ("force", "allow_force")):
        if payload.get(key) is not None:
            overrides[field] = bool(payload[key]) if key != "dry_run" else payload[key]

    effective_config = replace(config, **overrides) if overrides else config
    return (
        AgentContext(
            config=effective_config,
            db_handle=db_handle,
            intent_model=intent_model,
            sql_model=sql_model,
        ),
        effective_config,
    )


def _run_query_request(
    *,
    config: Any,
    db_handle: DatabaseHandle,
    intent_model: Any,
    sql_model: Any,
) -> Any:
    payload = request.get_json(force=True, silent=True) or {}
    question = payload.get("question")
    if not question:
        return jsonify({"ok": False, "error": "question is required"}), 400

    ctx, _ = _build_agent_context(
        config=config,
        db_handle=db_handle,
        intent_model=intent_model,
        sql_model=sql_model,
        payload=payload,
    )
    try:
        result = run_task(
            question=question,
            ctx=ctx,
            dry_run_override=payload.get("dry_run"),
            force=bool(payload.get("force", False)),
        )
    except SqlGuardViolation as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - unexpected path
        return jsonify({"ok": False, "error": str(exc)}), 500

    body = result_to_json(result, show_sql=True)
    status = 200
    if result.status == TaskStatus.UNSUPPORTED:
        status = 400
    elif result.status == TaskStatus.ERROR:
        status = 500
    return jsonify(body), status


def _database_identity(config: Any) -> dict[str, Any]:
    database: dict[str, Any] = {"backend": config.db_backend}
    if config.db_backend == "sqlite":
        database["path"] = config.db_path
    else:
        database["url"] = config.db_url
    return database


def create_app(base_overrides: dict[str, Any] | None = None) -> Flask:
    load_env_file()
    setup_logging()
    config = load_config(base_overrides or {})
    db_handle = init_sandbox_db(config)
    intent_model, sql_model = build_models(config)

    app = Flask(__name__)

    @app.post("/run")
    def run() -> Any:  # pragma: no cover - minimal API surface
        try:
            return _run_query_request(
                config=config,
                db_handle=db_handle,
                intent_model=intent_model,
                sql_model=sql_model,
            )
        except Exception as exc:  # pragma: no cover - unexpected path
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/query")
    def api_query() -> Any:
        return _run_query_request(
            config=config,
            db_handle=db_handle,
            intent_model=intent_model,
            sql_model=sql_model,
        )

    @app.get("/api/schema")
    def api_schema() -> Any:
        try:
            body = {
                "ok": True,
                "backend": config.db_backend,
                "database": _database_identity(config),
                "tables": db_handle.get_schema_overview(),
            }
            return jsonify(body), 200
        except Exception as exc:  # pragma: no cover - unexpected path
            return jsonify({"ok": False, "error": f"Failed to load schema overview: {exc}"}), 500

    @app.get("/api/examples")
    def api_examples() -> Any:
        return jsonify({"ok": True, "examples": EXAMPLE_QUERIES}), 200

    @app.get("/api/health")
    def api_health() -> Any:
        try:
            db_handle.execute_select("SELECT 1 AS ok")
            body = {
                "ok": True,
                "status": "healthy",
                "service": "sql-agent-demo",
                "database": {
                    "backend": config.db_backend,
                    "ready": True,
                },
                "config": {
                    "allow_write": config.allow_write,
                    "dry_run_default": config.dry_run_default,
                    "guard_level": config.guard_level,
                },
            }
            return jsonify(body), 200
        except Exception as exc:  # pragma: no cover - unexpected path
            body = {
                "ok": False,
                "status": "unhealthy",
                "service": "sql-agent-demo",
                "database": {
                    "backend": config.db_backend,
                    "ready": False,
                },
                "error": str(exc),
            }
            return jsonify(body), 500

    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SQL agent backend API. Recommended entrypoint: `uv run sql-agent-api --host 127.0.0.1 --port 8000`."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
