"""Command-line interface implementation for the SQL agent demo."""
from __future__ import annotations

import argparse
import sys
from typing import Iterable
import math
from pathlib import Path

from sql_agent_demo.core.models import (
    AgentContext,
    DbExecutionError,
    IntentType,
    LlmNotConfigured,
    StepTrace,
    SqlAgentError,
    SqlGuardViolation,
    TaskStatus,
)
from sql_agent_demo.core.sql_agent import run_task, run_write_query
from sql_agent_demo.infra.config import load_config
from sql_agent_demo.infra.db import init_sandbox_db
from sql_agent_demo.infra.env import load_env_file
from sql_agent_demo.infra.llm_provider import build_models
from sql_agent_demo.infra.logging import setup_logging
from sql_agent_demo.interfaces.dataset import load_query_file
from sql_agent_demo.interfaces.serialization import result_to_json


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-path", dest="db_path", type=str, help="Path to SQLite DB file.")
    parser.add_argument("--overwrite-db", dest="overwrite_db", action="store_true", help="Rebuild sandbox DB.")
    parser.add_argument("--max-rows", dest="max_rows", type=int, help="Max rows to return.")
    parser.add_argument("--top-k", dest="top_k", type=int, help="Schema table/column hint size.")
    parser.add_argument("--intent-model", dest="intent_model_name", type=str, help="Model name for intent detection.")
    parser.add_argument("--sql-model", dest="sql_model_name", type=str, help="Model name for SQL generation.")
    parser.add_argument("--trace", dest="allow_trace", action="store_true", help="Show trace even on success.")
    parser.add_argument("--selfcheck", dest="selfcheck_enabled", action="store_true", help="Enable SQL selfcheck.")
    parser.add_argument("--allow-write", dest="allow_write", action="store_true", help="Enable write operations.")
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        type=_bool_arg,
        nargs="?",
        const=True,
        default=None,
        help="Execute then roll back writes (default). Pass false to commit.",
    )
    parser.add_argument("--force", dest="force", action="store_true", help="Skip WHERE requirement (dangerous).")
    parser.add_argument("--json", dest="json_mode", action="store_true", help="Emit result as single-line JSON.")
    parser.add_argument(
        "--log-file",
        dest="log_file",
        type=str,
        help="Write detailed JSON (including trace) to this file.",
    )
    parser.add_argument(
        "--show-sql",
        dest="show_sql",
        action="store_true",
        help="Print executed SQL alongside summary.",
    )


def _bool_arg(val: str) -> bool:
    return str(val).lower() not in ("0", "false", "no", "off")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQL agent demo (read + guarded write).")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = False
    parser.set_defaults(command="ask")

    ask_parser = subparsers.add_parser("ask", help="Run a single question (default).")
    ask_parser.add_argument("question", type=str, help="User question in English.")
    _add_shared_arguments(ask_parser)

    file_parser = subparsers.add_parser("run-file", help="Run queries from a YAML/JSON file.")
    file_parser.add_argument("file", type=str, help="Path to YAML/JSON dataset with queries.")
    file_parser.add_argument("--limit", type=int, default=1, help="Run at most this many queries from the file.")
    _add_shared_arguments(file_parser)

    write_parser = subparsers.add_parser("write", help="Run a single write (INSERT/UPDATE/DELETE).")
    write_parser.add_argument("question", type=str, help="Write request in English.")
    _add_shared_arguments(write_parser)
    write_parser.set_defaults()

    argv = sys.argv[1:]
    known_commands = {"ask", "run-file", "write"}
    if argv and argv[0] not in known_commands and not argv[0].startswith("-"):
        argv = ["ask", *argv]

    return parser.parse_args(argv)


def _trace_lines(trace_steps: list[StepTrace]) -> list[str]:
    def _clean(text: str, limit: int = 160) -> str:
        flat = " ".join(text.split())
        return flat if len(flat) <= limit else f"{flat[:limit]}..."

    lines: list[str] = []
    for step in trace_steps:
        tokens: list[str] = []
        if step.prompt_tokens is not None or step.completion_tokens is not None or step.total_tokens is not None:
            p = step.prompt_tokens or 0
            c = step.completion_tokens or 0
            t = step.total_tokens or (p + c if (step.prompt_tokens is not None and step.completion_tokens is not None) else None)
            tok_parts = [f"{p}p", f"{c}c"]
            if t is not None:
                tok_parts.append(f"{t}t")
            tokens.append("/".join(tok_parts))
        if step.duration_ms is not None:
            tokens.append(f"{step.duration_ms:.1f}ms")

        metrics = f"[{', '.join(tokens)}]" if tokens else ""
        preview = _clean(step.output_preview) if step.output_preview else ""
        notes = f" ({step.notes})" if step.notes else ""

        if metrics and preview:
            lines.append(f"- {step.name} {metrics} -> {preview}{notes}")
        elif metrics:
            lines.append(f"- {step.name} {metrics}{notes}")
        elif preview:
            lines.append(f"- {step.name} -> {preview}{notes}")
        else:
            lines.append(f"- {step.name}{notes}")
    return lines


def _aggregate_metrics(steps: Iterable[StepTrace]) -> dict[str, float | int]:
    total_duration = 0.0
    prompt = 0
    completion = 0
    total = 0
    for step in steps:
        if step.duration_ms is not None:
            total_duration += step.duration_ms
        if step.prompt_tokens is not None:
            prompt += step.prompt_tokens
        if step.completion_tokens is not None:
            completion += step.completion_tokens
        if step.total_tokens is not None:
            total += step.total_tokens
        elif step.prompt_tokens is not None and step.completion_tokens is not None:
            total += step.prompt_tokens + step.completion_tokens

    return {
        "duration_ms": total_duration,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total if total > 0 else prompt + completion,
    }


def _print_cost(trace_steps: list[StepTrace]) -> None:
    if not trace_steps:
        return
    agg = _aggregate_metrics(trace_steps)
    dur = agg["duration_ms"]
    prompt = agg["prompt_tokens"]
    completion = agg["completion_tokens"]
    total = agg["total_tokens"]
    parts = []
    if dur and not math.isclose(dur, 0.0):
        parts.append(f"duration={dur:.1f}ms")
    parts.append(f"prompt_tokens={prompt}")
    parts.append(f"completion_tokens={completion}")
    parts.append(f"total_tokens={total}")
    print("Cost: " + ", ".join(parts))


def _print_result(result, show_trace: bool, show_sql: bool, json_mode: bool = False, log_file: str | None = None) -> int:
    trace_steps = result.trace or (result.query_result.trace if result.query_result else None) or []
    exit_code = 0
    if result.status == TaskStatus.UNSUPPORTED:
        exit_code = 2
    elif result.status != TaskStatus.SUCCESS:
        exit_code = 1

    if json_mode or log_file:
        payload = result_to_json(result, show_sql)
        line = json.dumps(payload, ensure_ascii=False)
        if json_mode:
            print(line)
        if log_file:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return exit_code
    if result.raw_question:
        print(f"Question: {result.raw_question}")

    if result.status != TaskStatus.SUCCESS or result.query_result is None:
        title = "Error"
        reason = result.error_message or "Task failed."
        hint = "Try rephrasing with the columns you need." if "fabricate" in reason.lower() else "Try a simpler read-only question."
        sql_preview = None
        for step in trace_steps:
            if step.name in ("generate_sql", "generate_write_sql") and step.output_preview:
                sql_preview = step.output_preview
                break
        print(f"{title}: {result.status.value}")
        print(f"Reason: {reason}")
        print(f"Hint: {hint}")
        if sql_preview:
            print(f"SQL: {sql_preview}")
        _print_cost(trace_steps)
        if (show_trace or result.status != TaskStatus.SUCCESS) and trace_steps:
            print("\nTrace:")
            for line in _trace_lines(trace_steps):
                print(line)
        return 1

    qr = result.query_result
    print(f"Summary: {qr.summary}")
    if show_sql:
        print(f"SQL: {qr.sql}")

    _print_cost(trace_steps)

    if show_trace and trace_steps:
        print("\nTrace:")
        for line in _trace_lines(trace_steps):
            print(line)
    return 0


def main() -> None:
    args = _parse_args()
    load_env_file()
    setup_logging()

    overrides = {
        "db_path": args.db_path,
        "overwrite_db": args.overwrite_db,
        "max_rows": args.max_rows,
        "top_k": args.top_k,
        "intent_model_name": args.intent_model_name,
        "sql_model_name": args.sql_model_name,
        "allow_trace": args.allow_trace,
        "selfcheck_enabled": args.selfcheck_enabled,
        "allow_write": getattr(args, "allow_write", None),
        "dry_run_default": getattr(args, "dry_run", None),
        "allow_force": getattr(args, "force", None),
    }

    config = load_config(overrides)

    try:
        db_handle = init_sandbox_db(config)
        intent_model, sql_model = build_models(config)
    except (LlmNotConfigured, SqlAgentError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    ctx = AgentContext(
        config=config,
        db_handle=db_handle,
        intent_model=intent_model,
        sql_model=sql_model,
    )

    if args.command == "write":
        force = bool(getattr(args, "force", False))
        dry_run = getattr(args, "dry_run", None)
        result = run_write_query(
            question=args.question,
            ctx=ctx,
            intent=IntentType.WRITE,
            traces=[],
            dry_run=dry_run,
            force=force,
        )
        code = _print_result(
            result,
            show_trace=args.allow_trace,
            show_sql=args.show_sql,
            json_mode=getattr(args, "json_mode", False),
            log_file=getattr(args, "log_file", None),
        )
        sys.exit(code)

    if args.command == "run-file":
        try:
            queries = load_query_file(args.file)
        except Exception as exc:
            print(f"[ERROR] Failed to read query file: {exc}", file=sys.stderr)
            sys.exit(1)

        limit = args.limit if args.limit and args.limit > 0 else len(queries)
        selected = queries[:limit]
        if not selected:
            print("[ERROR] No queries found in file.", file=sys.stderr)
            sys.exit(1)

        exit_code = 0
        for idx, item in enumerate(selected, start=1):
            name = item.get("name") or f"query-{idx}"
            print(f"[{idx}] {name}")
            try:
                result = run_task(question=item["question"], ctx=ctx)
            except (SqlGuardViolation, DbExecutionError) as exc:
                print(f"[ERROR] {exc}", file=sys.stderr)
                exit_code = 1
                continue
            code = _print_result(result, show_trace=args.allow_trace, show_sql=args.show_sql)
            exit_code = exit_code or code
            if idx < len(selected):
                print()

        sys.exit(exit_code)

    # Default: single question mode.
    try:
        result = run_task(
            question=args.question,
            ctx=ctx,
            dry_run_override=getattr(args, "dry_run", None),
            force=bool(getattr(args, "force", False)),
        )
    except (SqlGuardViolation, DbExecutionError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    exit_code = _print_result(
        result,
        show_trace=args.allow_trace,
        show_sql=args.show_sql,
        json_mode=getattr(args, "json_mode", False),
        log_file=getattr(args, "log_file", None),
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
