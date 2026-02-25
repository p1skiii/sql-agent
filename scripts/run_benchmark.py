import argparse, json, uuid, time, hashlib, os, re
from pathlib import Path
from collections import deque
import yaml

from sql_agent_demo.core.models import AgentContext
from sql_agent_demo.core.sql_agent import run_task
from sql_agent_demo.infra.config import load_config
from sql_agent_demo.infra.db import init_sandbox_db
from sql_agent_demo.infra.llm_provider import build_models
from sql_agent_demo.infra.env import load_env_file


def load_dataset(path):
    data = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def compute_config_hash(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


def aggregate_trace(trace):
    stages = {}
    def add(stage, dur, toks):
        s = stages.setdefault(stage, {"latency_ms": 0.0, "tokens": 0})
        s["latency_ms"] += dur or 0
        s["tokens"] += toks or 0
    total_tokens = 0
    for step in trace or []:
        name = getattr(step, "name", None) or step.get("name")
        dur = getattr(step, "duration_ms", None) if hasattr(step, "duration_ms") else step.get("duration_ms")
        toks = getattr(step, "total_tokens", None) if hasattr(step, "total_tokens") else step.get("total_tokens")
        total_tokens += toks or 0
        if name is None:
            stage = "other"
        elif name.startswith("intent"):
            stage = "intent"
        elif name in ("load_schema", "generate_sql", "generate_write_sql", "selfcheck", "repair_sql", "repair_after"):
            stage = "plan"
        elif name.startswith("execute"):
            stage = "execute"
        elif name.startswith("summarize"):
            stage = "summarize"
        else:
            stage = "other"
        add(stage, dur or 0, toks or 0)
    return stages, total_tokens


def extract_affected(trace_steps):
    affected = None
    probe = None
    dry_run = None
    guard_rule = None
    guard_reason = None
    for step in trace_steps or []:
        name = getattr(step, "name", None) or step.get("name")
        preview = getattr(step, "output_preview", None) if hasattr(step, "output_preview") else step.get("output_preview")
        if name in ("execute_write", "execute_write_probe") and preview:
            m = re.search(r"affected_rows=(\\d+)", preview)
            if m:
                val = int(m.group(1))
                if name == "execute_write_probe":
                    probe = val
                else:
                    affected = val
            m2 = re.search(r"dry_run=(true|false)", preview or "", re.IGNORECASE)
            if m2:
                dry_run = m2.group(1).lower() == "true"
        if name and "guard" in name.lower():
            guard_rule = name
            guard_reason = preview
    return probe, affected, dry_run, guard_rule, guard_reason


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tag", default="run")
    args = parser.parse_args()

    load_env_file()
    cfg_yaml = yaml.safe_load(Path(args.config).read_text())
    data = load_dataset(args.dataset)
    if args.limit:
        data = data[: args.limit]

    dataset_name = Path(args.dataset).stem
    out_path = Path(args.out) if args.out else Path(f"results/{dataset_name}__{args.tag}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done_ids = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    done_ids.add(obj.get("id"))
                except Exception:
                    continue

    base_overrides = cfg_yaml.get("config", {})
    config_hash = compute_config_hash(base_overrides)
    prompt_version = cfg_yaml.get("prompt_version", "v1")
    trace_version = cfg_yaml.get("trace_version", "v1")

    run_id = str(uuid.uuid4())
    fail_streak = 0
    rate_limit_streak = 0
    last50 = deque(maxlen=50)
    lat_hist = deque(maxlen=50)
    cooldown = False
    avg_base = [None]

    def stop_for_rates():
        nonlocal cooldown
        if len(last50) == 50:
            five_x = sum(1 for x in last50 if x >= 500)
            if five_x / 50 > 0.1:
                print("[STOP] 5xx ratio >10% in last 50; exiting")
                raise SystemExit(2)
        if lat_hist and len(lat_hist) >= 20:
            avg = sum(lat_hist) / len(lat_hist)
            if avg_base[0] is None:
                avg_base[0] = avg
            elif avg > 2 * avg_base[0]:
                cooldown = True
            else:
                cooldown = False

    def save(obj):
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Build base models/config once (single DB assumed, but db_path may be mutated per row)
    config = load_config(base_overrides)
    db_handle = init_sandbox_db(config)
    intent_model, sql_model = build_models(config)

    for item in data:
        if item.get("id") in done_ids:
            continue
        req_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        try:
            # if dataset provides db_id and a db_root in config, swap db_path
            db_root = cfg_yaml.get("db_root")
            if db_root and item.get("db_id"):
                candidate = Path(db_root) / item["db_id"] / f"{item['db_id']}.sqlite"
                if candidate.exists():
                    config.db_path = str(candidate)
                    db_handle = init_sandbox_db(config)
            ctx = AgentContext(config=config, db_handle=db_handle, intent_model=intent_model, sql_model=sql_model)
            result = run_task(question=item["question"], ctx=ctx)
            latency_ms = (time.perf_counter() - t0) * 1000
            trace_steps = result.trace or (result.query_result.trace if result.query_result else None) or []
            stages, total_tokens = aggregate_trace(trace_steps)
            probe_rows, affected_rows, dry_run, guard_rule, guard_reason = extract_affected(trace_steps)
            lat_hist.append(latency_ms)
            last50.append(200 if result.status.name == "SUCCESS" else 400)
            stop_for_rates()
            obj = {
                "id": item.get("id"),
                "dataset": dataset_name,
                "config_tag": args.tag,
                "run_id": run_id,
                "db_id": item.get("db_id"),
                "question": item.get("question"),
                "request_id": req_id,
                "ok": result.status.name == "SUCCESS",
                "status": result.status.value,
                "error_code": getattr(result, "error_code", None) or (result.status.value if result.status.name != "SUCCESS" else None),
                "reason": result.error_message,
                "sql": result.query_result.sql if result.query_result else None,
                "summary": result.query_result.summary if result.query_result else None,
                "latency_ms": latency_ms,
                "tokens": total_tokens,
                "stage_metrics": stages,
                "stage_latency_ms": {k: v.get("latency_ms") for k, v in stages.items()},
                "stage_tokens": {k: v.get("tokens") for k, v in stages.items()},
                "guard_hit": "GUARD" in (getattr(result, "error_code", "") or ""),
                "guard_rule": guard_rule,
                "guard_reason": guard_reason or result.error_message,
                "probe_rows": probe_rows,
                "affected_rows": affected_rows,
                "dry_run": dry_run,
                "repair_attempted": None,
                "repair_success": None,
                "model": config.sql_model_name,
                "base_url": os.environ.get("LLM_BASE_URL"),
                "trace_version": trace_version,
                "prompt_version": prompt_version,
                "config_hash": config_hash,
                "timestamp": time.time(),
            }
            save(obj)
            done_ids.add(item.get("id"))
            fail_streak = 0
            rate_limit_streak = 0
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            msg = str(exc)
            code = None
            if "429" in msg:
                rate_limit_streak += 1
                code = 429
            elif "500" in msg or "RemoteProtocolError" in msg:
                code = 500
            last50.append(code or 500)
            fail_streak += 1
            print(f"[WARN] id={item.get('id')} failed: {exc}")
            # persist the failure record to keep progress
            obj = {
                "id": item.get("id"),
                "dataset": dataset_name,
                "config_tag": args.tag,
                "run_id": run_id,
                "db_id": item.get("db_id"),
                "question": item.get("question"),
                "request_id": req_id,
                "ok": False,
                "status": "ERROR",
                "error_code": "EXCEPTION",
                "reason": msg,
                "sql": None,
                "summary": None,
                "latency_ms": latency_ms,
                "tokens": 0,
                "stage_metrics": {},
                "stage_latency_ms": {},
                "stage_tokens": {},
                "guard_hit": False,
                "guard_rule": None,
                "guard_reason": msg,
                "probe_rows": None,
                "affected_rows": None,
                "dry_run": None,
                "repair_attempted": None,
                "repair_success": None,
                "model": config.sql_model_name,
                "base_url": os.environ.get("LLM_BASE_URL"),
                "trace_version": trace_version,
                "prompt_version": prompt_version,
                "config_hash": config_hash,
                "timestamp": time.time(),
            }
            save(obj)
            done_ids.add(item.get("id"))
            if rate_limit_streak >= 3:
                wait = 1800
                print(f"[PAUSE] 429 x3, sleeping {wait}s")
                time.sleep(wait)
                rate_limit_streak = 0
            if fail_streak >= 10:
                print("[STOP] consecutive failures >=10")
                raise
            stop_for_rates()
            if cooldown:
                time.sleep(2)
            continue
        if cooldown:
            time.sleep(1)

if __name__ == "__main__":
    main()
