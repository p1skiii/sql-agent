"""Generate reproducible request/response audit samples and a report."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import socket
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "audit"
SAMPLES_DIR = AUDIT_DIR / "samples"
TMP_DIR = AUDIT_DIR / "_tmp"
REPORT_PATH = AUDIT_DIR / "report.md"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_SCRIPT = AUDIT_DIR / "backend_server.py"
API_CHAT_SCRIPT = AUDIT_DIR / "capture_api_chat.mjs"
SCHEMA_PATH = ROOT / "tests" / "data" / "schema.sql"
SEED_PATH = ROOT / "tests" / "data" / "seed.sql"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 18000


@dataclass(frozen=True)
class SampleCase:
    slug: str
    kind: str
    request_payload: dict[str, Any]
    db_name: str
    note: str
    before_query: str | None = None
    verification_request: dict[str, Any] | None = None


SAMPLE_CASES: tuple[SampleCase, ...] = (
    SampleCase(
        slug="read_success",
        kind="run_and_api",
        db_name="read_success.db",
        request_payload={
            "question": "Audit sample: list student ids and names",
            "allow_write": False,
            "dry_run": True,
            "force": False,
        },
        note="Baseline READ success sample.",
    ),
    SampleCase(
        slug="write_dry_run_success",
        kind="run_and_api",
        db_name="write_dry_run_success.db",
        request_payload={
            "question": "Audit sample: dry-run update Alice Johnson GPA to 3.9",
            "allow_write": True,
            "dry_run": True,
            "force": False,
        },
        note="Guarded WRITE dry-run success sample.",
    ),
    SampleCase(
        slug="write_commit_success",
        kind="run_and_api",
        db_name="write_commit_success.db",
        request_payload={
            "question": "Audit sample: commit update Alice Johnson GPA to 3.9",
            "allow_write": True,
            "dry_run": False,
            "force": False,
        },
        note="Guarded WRITE commit success sample with before/after verification.",
        before_query="SELECT name, gpa FROM students WHERE name = 'Alice Johnson'",
        verification_request={
            "question": "Audit sample: verify Alice Johnson GPA after commit",
            "allow_write": False,
            "dry_run": True,
            "force": False,
        },
    ),
    SampleCase(
        slug="unsupported",
        kind="run_and_api",
        db_name="unsupported.db",
        request_payload={
            "question": "Audit sample: unsupported write when writes are disabled",
            "allow_write": False,
            "dry_run": True,
            "force": False,
        },
        note="Business-policy rejection path with TaskStatus.UNSUPPORTED.",
    ),
    SampleCase(
        slug="error",
        kind="run_and_api",
        db_name="error.db",
        request_payload={
            "question": "Audit sample: error write with an invalid column",
            "allow_write": True,
            "dry_run": True,
            "force": False,
        },
        note="Execution error path with TaskStatus.ERROR.",
    ),
    SampleCase(
        slug="bad_request_validation",
        kind="run_and_api",
        db_name="bad_request_validation.db",
        request_payload={},
        note="Direct API validation error path outside result_to_json.",
    ),
)


DOCUMENTED_RUN_FIELDS: tuple[str, ...] = (
    "id",
    "dataset",
    "db_id",
    "config_tag",
    "run_id",
    "request_id",
    "question",
    "sql",
    "summary",
    "ok",
    "status",
    "error_code",
    "reason",
    "model",
    "base_url",
    "prompt_version",
    "trace_version",
    "config_hash",
    "timestamp",
    "tokens",
    "latency_ms",
    "stage_latency_ms",
    "stage_tokens",
    "guard_hit",
    "guard_rule",
    "guard_reason",
    "probe_rows",
    "affected_rows",
    "dry_run",
    "repair_attempted",
    "repair_success",
)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_format_json(payload), encoding="utf-8")


def _http_post_json(url: str, payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    with tempfile.TemporaryDirectory(dir=str(TMP_DIR)) as tmpdir:
        header_path = Path(tmpdir) / "headers.txt"
        body_path = Path(tmpdir) / "body.json"
        cmd = [
            "curl",
            "-sS",
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "--data",
            json.dumps(payload),
            "-D",
            str(header_path),
            "-o",
            str(body_path),
            "-w",
            "%{http_code}|%{content_type}",
        ]
        completed = subprocess.run(
            cmd,
            check=True,
            text=True,
            capture_output=True,
            timeout=30,
        )

        status_text, content_type = completed.stdout.strip().split("|", maxsplit=1)
        status = int(status_text)
        raw = body_path.read_text(encoding="utf-8")
        payload_obj = json.loads(raw)

    http_info = {
        "status_code": status,
        "content_type": content_type or None,
        "ok": 200 <= status < 300,
    }
    return http_info, payload_obj


def _wait_for_backend(url: str, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _http_post_json(url, {})
            return
        except Exception as exc:  # pragma: no cover - startup loop
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _run_query(db_path: Path, sql: str) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)
        columns = [col[0] for col in cursor.description or []]
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
    return {"sql": sql, "columns": columns, "rows": rows}


def _ensure_frontend_deps() -> None:
    if not (FRONTEND_DIR / "node_modules").exists():
        raise RuntimeError(
            "frontend/node_modules is missing. Run `pnpm install` in frontend/ before generating audit samples."
        )


def _ensure_next_server_alias() -> None:
    alias_path = FRONTEND_DIR / "node_modules" / "next" / "server"
    if alias_path.exists():
        return
    alias_path.symlink_to("server.js")


def _capture_api_chat_response(payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    completed = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            str(API_CHAT_SCRIPT),
            json.dumps(payload),
            f"http://{BACKEND_HOST}:{BACKEND_PORT}/run",
        ],
        cwd=str(ROOT),
        check=True,
        text=True,
        capture_output=True,
        timeout=30,
    )
    parsed = json.loads(completed.stdout)
    return (
        {
            "status_code": parsed["status_code"],
            "content_type": parsed["content_type"],
            "ok": parsed["ok"],
        },
        parsed["body"],
    )


def _start_backend(db_path: Path) -> subprocess.Popen[str]:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    log_path = TMP_DIR / f"backend-{db_path.stem}.log"
    log_file = log_path.open("w", encoding="utf-8")
    print(f"Starting backend server for {db_path.name}...", flush=True)
    proc = subprocess.Popen(
        [
            sys.executable,
            str(BACKEND_SCRIPT),
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
            "--db-path",
            str(db_path),
            "--schema-path",
            str(SCHEMA_PATH),
            "--seed-path",
            str(SEED_PATH),
        ],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=True,
    )
    try:
        _wait_for_backend(f"http://{BACKEND_HOST}:{BACKEND_PORT}/run")
    except Exception:
        _stop_process(proc)
        raise
    print(f"Backend server is ready for {db_path.name}.", flush=True)
    return proc


def _stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - cleanup path
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)


def _wait_for_port_closed(host: str, port: int, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) != 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {host}:{port} to close")


def _collect_sample(case: SampleCase) -> dict[str, Any]:
    print(f"Collecting sample: {case.slug}", flush=True)
    sample_dir = SAMPLES_DIR / case.slug
    if sample_dir.exists():
        shutil.rmtree(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)

    _write_json(sample_dir / "request.json", case.request_payload)

    db_path = TMP_DIR / case.db_name
    if db_path.exists():
        db_path.unlink()

    before_state = None
    verification_artifact = None
    backend_proc = _start_backend(db_path)
    try:
        if case.before_query:
            before_state = _run_query(db_path, case.before_query)
            _write_json(sample_dir / "db_before.json", before_state)

        run_http, run_response = _http_post_json(
            f"http://{BACKEND_HOST}:{BACKEND_PORT}/run",
            case.request_payload,
        )
        _write_json(sample_dir / "run_http.json", run_http)
        _write_json(sample_dir / "run_response.json", run_response)

        api_http, api_response = _capture_api_chat_response(case.request_payload)
        _write_json(sample_dir / "api_chat_http.json", api_http)
        _write_json(sample_dir / "api_chat_response.json", api_response)

        if case.before_query:
            after_state = _run_query(db_path, case.before_query)
            _write_json(sample_dir / "db_after.json", after_state)
            if case.verification_request is None:
                raise RuntimeError(f"{case.slug} is missing verification_request")
            verification_http, verification_response = _http_post_json(
                f"http://{BACKEND_HOST}:{BACKEND_PORT}/run",
                case.verification_request,
            )
            verification_artifact = {
                "request": case.verification_request,
                "run_http": verification_http,
                "run_response": verification_response,
            }
            _write_json(sample_dir / "verification_read.json", verification_artifact)
    finally:
        _stop_process(backend_proc)
        _wait_for_port_closed(BACKEND_HOST, BACKEND_PORT)

    return {
        "slug": case.slug,
        "note": case.note,
        "request": case.request_payload,
        "run_http": json.loads((sample_dir / "run_http.json").read_text(encoding="utf-8")),
        "run_response": json.loads((sample_dir / "run_response.json").read_text(encoding="utf-8")),
        "api_http": json.loads((sample_dir / "api_chat_http.json").read_text(encoding="utf-8")),
        "api_response": json.loads((sample_dir / "api_chat_response.json").read_text(encoding="utf-8")),
        "before_state": before_state,
        "verification_read": verification_artifact,
    }


def _collect_field_stats(objects: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    total = 0
    for obj in objects:
        total += 1
        for key, value in obj.items():
            entry = stats.setdefault(
                key,
                {"present": 0, "types": set(), "example": value},
            )
            entry["present"] += 1
            entry["types"].add(_json_type(value))
    for entry in stats.values():
        entry["presence"] = "always" if entry["present"] == total else "conditional"
        entry["observed_type"] = " | ".join(sorted(entry["types"]))
    return stats


def _render_field_rows(
    stats: dict[str, dict[str, Any]],
    *,
    include_missing: Iterable[str] = (),
) -> list[str]:
    rows = [
        "| Field | Presence | Observed type | Example value | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key in sorted(stats):
        entry = stats[key]
        example = json.dumps(entry["example"], ensure_ascii=False)
        note = ""
        if key == "affected_rows" and entry["observed_type"] == "null":
            note = "Observed as null in every sampled write response."
        elif key == "error":
            note = "String content is not shape-stable: plain message for local validation, serialized backend JSON for proxied failures."
        rows.append(
            f"| `{key}` | {entry['presence']} | `{entry['observed_type']}` | `{example}` | {note} |"
        )
    for missing in include_missing:
        if missing not in stats:
            rows.append(
                f"| `{missing}` | missing but should exist | `absent` | `n/a` | Documented in `docs/api_contract.md` but absent from all sampled `/run` bodies. |"
            )
    return rows


def _render_http_rows(collected: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| Sample | Route | Status | Content-Type | Body shape |",
        "| --- | --- | --- | --- | --- |",
    ]
    for sample in collected:
        run_shape = ", ".join(sorted(sample["run_response"].keys()))
        api_shape = ", ".join(sorted(sample["api_response"].keys()))
        rows.append(
            f"| `{sample['slug']}` | `/run` | {sample['run_http']['status_code']} | `{sample['run_http']['content_type']}` | `{run_shape}` |"
        )
        rows.append(
            f"| `{sample['slug']}` | `/api/chat` | {sample['api_http']['status_code']} | `{sample['api_http']['content_type']}` | `{api_shape}` |"
        )
    return rows


def _render_display_contract() -> str:
    return """## Recommended Display Contract

### Result Card: always safe now
- `/api/chat` success: `summary`
- `/api/chat` failure: `error`
- `/api/chat` success-only raw state when present: `raw.status`, `raw.mode`, `raw.reason`

### SQL Panel: safe only when present
- `raw.sql`
- `raw.raw_sql`
- `raw.repaired_sql`

### Write Evidence: safe only with verification
- `audit/samples/write_commit_success/db_before.json`
- `audit/samples/write_commit_success/db_after.json`
- `audit/samples/write_commit_success/verification_read.json`

### Trace Panel: safe but optional
- `raw.trace`

### UI Must Not Rely On
- `raw.affected_rows` exactness
- `raw.diagnosis` completeness
- `raw.repaired_sql` existence
- a single top-level `/api/chat` shape for both success and failure
"""


def _render_report(collected: list[dict[str, Any]]) -> str:
    run_objects = [sample["run_response"] for sample in collected]
    api_objects = [sample["api_response"] for sample in collected]
    raw_objects = [sample["api_response"]["raw"] for sample in collected if isinstance(sample["api_response"].get("raw"), dict)]

    run_stats = _collect_field_stats(run_objects)
    api_stats = _collect_field_stats(api_objects)
    raw_stats = _collect_field_stats(raw_objects)

    missing_run_fields = [field for field in DOCUMENTED_RUN_FIELDS if field not in run_stats]

    sample_rows = [
        "| Sample | Request payload | `/run` status | `/api/chat` status | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for sample in collected:
        request_text = json.dumps(sample["request"], ensure_ascii=False)
        sample_rows.append(
            f"| `{sample['slug']}` | `{request_text}` | {sample['run_http']['status_code']} | {sample['api_http']['status_code']} | {sample['note']} |"
        )

    commit_notes = []
    commit_sample = next(sample for sample in collected if sample["slug"] == "write_commit_success")
    before_rows = commit_sample["before_state"]["rows"] if commit_sample["before_state"] else []
    verification = commit_sample["verification_read"]
    if before_rows:
        commit_notes.append(f"- Before commit: `{json.dumps(before_rows, ensure_ascii=False)}`")
    if verification is not None:
        commit_notes.append(
            f"- Verification read summary: `{verification['run_response'].get('summary')}` with status `{verification['run_http']['status_code']}`"
        )
    after_db_rows = json.loads((SAMPLES_DIR / "write_commit_success" / "db_after.json").read_text(encoding="utf-8"))["rows"]
    commit_notes.append(f"- After commit DB rows: `{json.dumps(after_db_rows, ensure_ascii=False)}`")

    sections = [
        "# Response Audit Report",
        "",
        "Generated from deterministic request/reply samples captured through the real `/run` Flask route and the real `/api/chat` Next route.",
        "",
        "## Sample Inventory",
        *sample_rows,
        "",
        "## HTTP Behavior",
        * _render_http_rows(collected),
        "",
        "Key observations:",
        "- `/run` success returns HTTP 200 with the `result_to_json(...)` shape.",
        "- `/run` unsupported returns HTTP 400 with the same `result_to_json(...)` envelope.",
        "- `/run` execution error returns HTTP 500 with the same `result_to_json(...)` envelope.",
        "- `/run` bad request validation returns HTTP 400 with a different direct body: `{ok:false,error:...}`.",
        "- `/api/chat` success returns HTTP 200 with `{summary, raw}`.",
        "- `/api/chat` has its own request validation for missing `question`, returning HTTP 400 with a minimal `{error}` body before any backend call.",
        "- For backend-proxied failures, `/api/chat` mirrors the backend status code but wraps the entire backend JSON body into a string field: `{error: \"...raw backend JSON...\"}`.",
        "",
        "## `/run` Field Inventory",
        * _render_field_rows(run_stats, include_missing=missing_run_fields),
        "",
        "## `/api/chat` Top-Level Field Inventory",
        * _render_field_rows(api_stats),
        "",
        "## `/api/chat.raw` Field Inventory",
        "This section covers success-only `raw` objects. Failure responses do not include `raw` at all.",
        * _render_field_rows(raw_stats),
        "",
        "## Write Commit Evidence",
        *commit_notes,
        "",
        "## Current Mismatches",
        "- `docs/api_contract.md` documents many fields that do not appear in the sampled runtime `/run` bodies.",
        "- `/api/chat` drops stable top-level backend fields on success and exposes them only under `raw`.",
        "- `/api/chat` does not preserve the backend JSON envelope on failure; it stringifies the full backend body into `error`.",
        "- `affected_rows` stays `null` in all sampled write-success `/run` bodies even when writes clearly affect one row.",
        "",
        _render_display_contract(),
    ]
    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate audit samples and report.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing audit/sample artifacts before regeneration.",
    )
    args = parser.parse_args()

    if args.clean:
        shutil.rmtree(SAMPLES_DIR, ignore_errors=True)
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating audit samples...", flush=True)
    _ensure_frontend_deps()
    _ensure_next_server_alias()
    collected = [_collect_sample(case) for case in SAMPLE_CASES]

    REPORT_PATH.write_text(_render_report(collected), encoding="utf-8")
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print(f"Wrote report to {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
