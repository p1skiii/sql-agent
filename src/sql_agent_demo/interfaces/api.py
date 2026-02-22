"""Thin Flask API exposing the same JSON schema as the CLI."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from typing import Any

from flask import Flask, jsonify, request

from sql_agent_demo.core.models import AgentContext, SqlGuardViolation, TaskStatus
from sql_agent_demo.core.sql_agent import run_task
from sql_agent_demo.infra.config import load_config
from sql_agent_demo.infra.db import init_sandbox_db
from sql_agent_demo.infra.env import load_env_file
from sql_agent_demo.infra.llm_provider import build_models
from sql_agent_demo.infra.logging import setup_logging
from sql_agent_demo.interfaces.serialization import result_to_json


def create_app(base_overrides: dict[str, Any] | None = None) -> Flask:
    load_env_file()
    setup_logging()
    config = load_config(base_overrides or {})
    db_handle = init_sandbox_db(config)
    intent_model, sql_model = build_models(config)

    app = Flask(__name__)

    @app.post("/run")
    def run() -> Any:  # pragma: no cover - minimal API surface
        payload = request.get_json(force=True, silent=True) or {}
        question = payload.get("question")
        if not question:
            return jsonify({"ok": False, "error": "question is required"}), 400

        overrides = {}
        for key, field in (("allow_write", "allow_write"), ("dry_run", "dry_run_default"), ("force", "allow_force")):
            if payload.get(key) is not None:
                overrides[field] = bool(payload[key]) if key != "dry_run" else payload[key]

        cfg = replace(config, **overrides) if overrides else config
        ctx = AgentContext(
            config=cfg,
            db_handle=db_handle,
            intent_model=intent_model,
            sql_model=sql_model,
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

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="SQL agent HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
