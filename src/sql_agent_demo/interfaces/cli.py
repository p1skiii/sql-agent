"""CLI for AMP task protocol."""
from __future__ import annotations

import argparse
import json
import sys

from sql_agent_demo.core.factory import build_task_service
from sql_agent_demo.infra.config import load_config
from sql_agent_demo.infra.env import load_env_file
from sql_agent_demo.infra.llm_provider import build_models_optional
from sql_agent_demo.infra.logging import setup_logging
from sql_agent_demo.interfaces.serialization import state_to_response


def _bool_arg(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AMP task CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("task-plan", help="Create and plan a task.")
    plan.add_argument("question", type=str)
    plan.add_argument("--session-id", type=str, default="default")
    plan.add_argument("--db-target", type=str, default=None)
    plan.add_argument("--language", type=str, default="auto")
    plan.add_argument("--json", action="store_true")

    confirm = subparsers.add_parser("task-confirm", help="Confirm a pending task.")
    confirm.add_argument("task_id", type=str)
    confirm.add_argument("--approve", type=_bool_arg, default=True)
    confirm.add_argument("--comment", type=str, default=None)
    confirm.add_argument("--json", action="store_true")

    show = subparsers.add_parser("task-show", help="Show a task by id.")
    show.add_argument("task_id", type=str)
    show.add_argument("--json", action="store_true")

    parser.add_argument("--db-backend", type=str, default=None)
    parser.add_argument("--db-url", type=str, default=None)
    parser.add_argument("--max-rows", type=int, default=None)
    return parser.parse_args()


def _print_payload(payload: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"task_id: {payload.get('task_id')}")
    print(f"status: {payload.get('status')}")
    print(f"risk_level: {payload.get('risk_level')}")
    if payload.get("thinking_summary"):
        print(f"thinking_summary: {payload['thinking_summary']}")
    if payload.get("workflow"):
        print("workflow:")
        for item in payload["workflow"]:
            print(f"  - {item['step']} ({item['agent']}): {item['purpose']}")
    if payload.get("result"):
        print("result:")
        print(json.dumps(payload["result"], ensure_ascii=False, indent=2))
    if payload.get("proposal"):
        print("proposal:")
        print(json.dumps(payload["proposal"], ensure_ascii=False, indent=2))
    if payload.get("error"):
        print("error:")
        print(json.dumps(payload["error"], ensure_ascii=False, indent=2))


def main() -> None:
    args = _parse_args()
    load_env_file()
    setup_logging()

    config = load_config(
        {
            "db_backend": args.db_backend,
            "db_url": args.db_url,
            "max_rows": args.max_rows,
        }
    )

    intent_model, sql_model = build_models_optional(config)
    try:
        service = build_task_service(config, intent_model=intent_model, sql_model=sql_model)
    except Exception as exc:
        print(f"[ERROR] failed to build task service: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.command == "task-plan":
        state = service.plan_task(
            question=args.question,
            session_id=args.session_id,
            db_target=args.db_target or config.db_target,
            language=args.language,
        )
        payload = state_to_response(state)
        payload["ok"] = state.status.value == "SUCCEEDED"
        _print_payload(payload, args.json)
        sys.exit(0 if payload["ok"] else 2)

    if args.command == "task-confirm":
        state = service.confirm_task(task_id=args.task_id, approve=args.approve, comment=args.comment)
        payload = state_to_response(state)
        payload["ok"] = state.status.value == "SUCCEEDED"
        _print_payload(payload, args.json)
        sys.exit(0 if payload["ok"] else 2)

    state = service.get_task(args.task_id)
    if state is None:
        print(json.dumps({"ok": False, "error": "task not found", "task_id": args.task_id}, ensure_ascii=False))
        sys.exit(1)

    payload = state_to_response(state)
    payload["ok"] = state.status.value == "SUCCEEDED"
    _print_payload(payload, args.json)
    sys.exit(0 if payload["ok"] else 2)


if __name__ == "__main__":
    main()
