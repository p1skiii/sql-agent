"""Flask API for AMP task protocol."""
from __future__ import annotations

import argparse
from typing import Any

from flask import Flask, jsonify, request

from sql_agent_demo.core.factory import build_task_service
from sql_agent_demo.core.models import AgentConfig
from sql_agent_demo.infra.config import load_config
from sql_agent_demo.infra.env import load_env_file
from sql_agent_demo.infra.llm_provider import build_models_optional
from sql_agent_demo.infra.logging import setup_logging
from sql_agent_demo.interfaces.serialization import state_to_response, status_code_for_state


def _deprecated_response() -> tuple[Any, int]:
    return (
        jsonify(
            {
                "ok": False,
                "error": "This endpoint is deprecated. Use /api/tasks/plan and /api/tasks/{task_id}/confirm.",
            }
        ),
        410,
    )


def create_app(*, config: AgentConfig | None = None, service: Any | None = None) -> Flask:
    app = Flask(__name__)

    active_config = config or load_config()
    active_service = service
    boot_error: str | None = None

    if active_service is None:
        try:
            intent_model, sql_model = build_models_optional(active_config)
            active_service = build_task_service(active_config, intent_model=intent_model, sql_model=sql_model)
        except Exception as exc:  # pragma: no cover - deployment path
            boot_error = str(exc)

    @app.post("/run")
    def deprecated_run() -> Any:
        return _deprecated_response()

    @app.post("/api/query")
    def deprecated_query() -> Any:
        return _deprecated_response()

    @app.post("/api/tasks/plan")
    def api_task_plan() -> Any:
        if active_service is None:
            return jsonify({"ok": False, "error": boot_error or "service unavailable"}), 503

        payload = request.get_json(force=True, silent=True) or {}
        question = str(payload.get("question", "")).strip()
        if not question:
            return jsonify({"ok": False, "error": "question is required"}), 400

        session_id = str(payload.get("session_id") or "default")
        db_target = str(payload.get("db_target") or active_config.db_target)
        language = str(payload.get("language") or "auto")

        state = active_service.plan_task(
            question=question,
            session_id=session_id,
            db_target=db_target,
            language=language,
        )
        body = state_to_response(state)
        body["ok"] = state.status.value == "SUCCEEDED"
        return jsonify(body), status_code_for_state(state)

    @app.post("/api/tasks/<task_id>/confirm")
    def api_task_confirm(task_id: str) -> Any:
        if active_service is None:
            return jsonify({"ok": False, "error": boot_error or "service unavailable"}), 503

        payload = request.get_json(force=True, silent=True) or {}
        approve = bool(payload.get("approve", False))
        comment = payload.get("comment")
        comment_text = str(comment) if comment is not None else None

        state = active_service.confirm_task(task_id=task_id, approve=approve, comment=comment_text)
        body = state_to_response(state)
        body["ok"] = state.status.value == "SUCCEEDED"
        return jsonify(body), status_code_for_state(state)

    @app.get("/api/tasks/<task_id>")
    def api_task_status(task_id: str) -> Any:
        if active_service is None:
            return jsonify({"ok": False, "error": boot_error or "service unavailable"}), 503

        state = active_service.get_task(task_id)
        if state is None:
            return jsonify({"ok": False, "error": "task not found", "task_id": task_id}), 404

        body = state_to_response(state)
        body["ok"] = state.status.value == "SUCCEEDED"
        return jsonify(body), status_code_for_state(state)

    @app.get("/api/health")
    def api_health() -> Any:
        if active_service is None:
            return jsonify({"ok": False, "status": "unhealthy", "error": boot_error or "service unavailable"}), 503

        return (
            jsonify(
                {
                    "ok": True,
                    "status": "healthy",
                    "service": "sql-agent-amp",
                    "database": {"backend": active_config.db_backend, "target": active_config.db_target},
                }
            ),
            200,
        )

    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AMP task API")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_env_file()
    setup_logging()
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
