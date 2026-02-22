"""SQL agent pipelines for read-only queries."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence
import re
import time

from .intent import detect_intent
from .models import (
    AgentContext,
    DbExecutionError,
    IntentType,
    QueryResult,
    SelfCheckResult,
    SeverityLevel,
    StepTrace,
    TaskResult,
    TaskStatus,
    SqlGuardViolation,
)
from .safety import validate_readonly_sql, validate_write_sql
from .summarizer import summarize


@dataclass
class SqlGenerationResult:
    sql: str
    tables: list[str] | None = None
    assumptions: str | None = None
    kind: str | None = None


def _preview(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else f"{text[:limit]}..."


def _metric_fields(metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = metrics or {}
    return {
        "duration_ms": metrics.get("duration_ms"),
        "prompt_tokens": metrics.get("prompt_tokens"),
        "completion_tokens": metrics.get("completion_tokens"),
        "total_tokens": metrics.get("total_tokens"),
    }


def _last_metrics(model: Any) -> dict[str, Any] | None:
    metrics = getattr(model, "last_metrics", None)
    return metrics if isinstance(metrics, dict) else None


@dataclass
class TokenBudget:
    max_step_tokens: int | None
    max_total_tokens: int | None
    total_tokens: int = 0

    def record(self, metrics: dict[str, Any] | None, step: str) -> str | None:
        if not metrics:
            return None
        step_total = metrics.get("total_tokens")
        if step_total is None and metrics.get("prompt_tokens") is not None and metrics.get("completion_tokens") is not None:
            step_total = metrics["prompt_tokens"] + metrics["completion_tokens"]

        if self.max_step_tokens and step_total and step_total > self.max_step_tokens:
            return f"Token budget exceeded at {step}: total_tokens={step_total} > max_step_tokens={self.max_step_tokens}"

        if step_total:
            self.total_tokens += step_total

        if self.max_total_tokens and self.total_tokens > self.max_total_tokens:
            return f"Token budget exceeded: accumulated_tokens={self.total_tokens} > max_total_tokens={self.max_total_tokens}"
        return None


def _compress_schema_line(line: str) -> str:
    """Format 'table: col, col2' into 'table(col, col2, ...)' keeping all columns."""
    if ":" not in line:
        return line.strip()
    table, cols_text = line.split(":", 1)
    cols = [col.strip() for col in cols_text.split(",") if col.strip()]

    inner = ", ".join([col.split("(", 1)[0].strip() for col in cols])
    return f"{table.strip()}({inner})"


def select_schema_subset(question: str, full_schema: str, top_k: int = 3, max_columns: int = 4) -> str:
    """Return a lightweight schema slice most relevant to the question."""
    lines = [line.strip() for line in full_schema.splitlines() if line.strip()]
    if not lines:
        return full_schema

    tokens = [t for t in re.split(r"[^a-zA-Z0-9_]+", question.lower()) if t]
    scored: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        score = sum(1 for token in tokens if token and token in line.lower())
        scored.append((score, idx, line))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [line for score, _, line in scored if score > 0][:top_k]
    if not selected:
        selected = lines[:top_k]

    compressed = [_compress_schema_line(line) for line in selected]
    return "\n".join(compressed)


def _generate_sql_with_llm(
    question: str, schema_snippet: str, model: Any, top_k: int, strict: bool = False
) -> SqlGenerationResult | None:
    system_prompt = (
        "You are an expert SQL assistant. Generate a single SQL query that answers the user's question. "
        "Rules: only output one SELECT statement; do not include any write operations (INSERT, UPDATE, DELETE, DROP, "
        "ALTER, TRUNCATE, CREATE). If the request is not read-only, respond with ONLY_READ_ONLY_SUPPORTED. "
        "Do not fabricate columns or return hard-coded placeholder values; always select real columns such as instructor when asked. "
        "Respond ONLY with JSON: {\"sql\": \"...\", \"tables\": [\"...\"], \"assumptions\": \"...\"}."
    )
    if strict:
        system_prompt += " Never use NULL or string literals with AS column aliases; use existing columns only."
    user_prompt = (
        f"Database schema (top {top_k} tables/columns):\n{schema_snippet}\n\n"
        f"Question: {question}\nReturn only JSON."
    )

    payload = model.generate_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    if not isinstance(payload, dict):
        return None

    sql_text = str(payload.get("sql", "")).strip()
    if not sql_text:
        return None

    text = sql_text
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
        text = text.replace("sql", "", 1).strip() if text.lower().startswith("sql") else text

    tables = payload.get("tables")
    if tables is not None and not isinstance(tables, list):
        tables = None

    assumptions = payload.get("assumptions")
    assumptions = str(assumptions) if assumptions is not None else None

    return SqlGenerationResult(sql=text, tables=tables, assumptions=assumptions)


def _generate_write_sql(
    question: str, schema_snippet: str, model: Any, top_k: int
) -> SqlGenerationResult | None:
    system_prompt = (
        "You are an expert SQL assistant. Generate ONE safe data-modifying statement (INSERT, UPDATE, or DELETE). "
        "Rules: only one statement; UPDATE/DELETE must include a WHERE clause; never use DROP/ALTER/TRUNCATE/DDL; "
        "do not fabricate columns; respond ONLY with JSON: {\"sql\": \"...\", \"tables\": [\"...\"], \"assumptions\": \"...\"}."
    )
    user_prompt = (
        f"Database schema (top {top_k} tables/columns):\n{schema_snippet}\n\n"
        f"Question: {question}\nReturn only JSON."
    )

    payload = model.generate_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    if not isinstance(payload, dict):
        return None

    sql_text = str(payload.get("sql", "")).strip()
    if not sql_text:
        return None

    text = sql_text
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
        text = text.replace("sql", "", 1).strip() if text.lower().startswith("sql") else text

    tables = payload.get("tables")
    if tables is not None and not isinstance(tables, list):
        tables = None

    assumptions = payload.get("assumptions")
    assumptions = str(assumptions) if assumptions is not None else None

    return SqlGenerationResult(sql=text, tables=tables, assumptions=assumptions, kind="write")


def _needs_llm_summary(question: str) -> bool:
    text = question.lower()
    return any(trigger in text for trigger in ("explain", "why", "reason", "interpret", "summarize", "insight"))


def _has_constant_projection(sql: str, column: str) -> bool:
    """Detect constant projections like 'x' AS column or NULL AS column."""
    pattern = re.compile(
        rf"(?:'[^']*'|\"[^\"]*\"|NULL)\s+AS\s+{re.escape(column)}\b", re.IGNORECASE
    )
    return bool(pattern.search(sql))


def _schema_has_column(full_schema: str, column: str) -> bool:
    col_l = column.lower()
    for line in full_schema.splitlines():
        parts = line.split(":")
        if len(parts) < 2:
            continue
        cols_part = parts[1]
        cols = [c.strip().lower() for c in cols_part.split(",") if c.strip()]
        if col_l in cols:
            return True
    return False


DEFAULT_PROJECTIONS: dict[str, list[str]] = {
    "students": ["name"],
    "courses": ["title", "instructor"],
}


_KNOWN_FIELD_TOKENS = {
    "name",
    "gpa",
    "city",
    "major",
    "id",
    "email",
    "address",
    "salary",
    "phone",
}


def _parse_schema_columns(full_schema: str) -> set[str]:
    cols: set[str] = set()
    for line in full_schema.splitlines():
        if ":" not in line:
            continue
        _, cols_text = line.split(":", 1)
        for col in cols_text.split(","):
            col_clean = col.strip().split(" ")[0]
            if col_clean:
                cols.add(col_clean.lower())
    return cols


def _should_allow_all_columns(question: str) -> bool:
    text = question.lower()
    return any(
        phrase in text
        for phrase in (
            "all columns",
            "full details",
            "full info",
            "everything",
            "every column",
            "all fields",
        )
    )


def _shape_sql(sql: str, question: str, default_limit: int) -> tuple[str, str | None]:
    """Apply projection and LIMIT shaping. Returns (sql, note)."""
    note = None
    shaped = sql
    allow_all = _should_allow_all_columns(question)

    table_match = re.search(r"\bfrom\s+([a-zA-Z_][\w]*)", sql, flags=re.IGNORECASE)
    table = table_match.group(1) if table_match else None
    projection = DEFAULT_PROJECTIONS.get(table.lower()) if table else None

    select_match = re.match(r"\s*select\s+(distinct\s+)?(.+?)\s+from\s+", sql, flags=re.IGNORECASE | re.DOTALL)
    if select_match and projection and not allow_all:
        body = select_match.group(2).strip()
        body_lower = body.lower()
        table_variants = [f"{table}.*", f'"{table}".*', f"`{table}`.*", "*"] if table else ["*"]
        if body_lower in table_variants:
            new_body = ", ".join([f"{table}.{c}" if table else c for c in projection])
            shaped = sql.replace(body, new_body, 1)
            note = f"projection shaped to {', '.join(projection)}"

    if default_limit and re.search(r"\blimit\b", shaped, flags=re.IGNORECASE) is None:
        shaped = shaped.rstrip().rstrip(";")
        shaped = f"{shaped} LIMIT {default_limit}"
        note = (note + "; " if note else "") + f"limit {default_limit}"

    return shaped, note


def _shape_student_insert(sql: str) -> tuple[str, str | None]:
    """Ensure INSERT into students includes required NOT NULL columns with defaults."""
    pattern = re.compile(
        r"insert\s+into\s+students\s*(\(([^)]*)\))?\s*values\s*\(([^)]*)\)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    if not match:
        return sql, None

    cols_part = match.group(2)
    vals_part = match.group(3)
    if vals_part is None:
        return sql, None

    cols = []
    if cols_part:
        cols = [c.strip().strip("`\"") for c in cols_part.split(",") if c.strip()]
    vals = [v.strip() for v in vals_part.split(",")]

    col_to_val = {col.lower(): vals[idx] for idx, col in enumerate(cols) if idx < len(vals)}

    required = ["name", "city", "major", "gpa"]
    defaults = {
        "city": "'Unknown'",
        "major": "'Undeclared'",
        "gpa": "0.0",
    }

    shaped_cols: list[str] = []
    shaped_vals: list[str] = []
    for col in required:
        shaped_cols.append(col)
        if col in col_to_val:
            shaped_vals.append(col_to_val[col])
        else:
            shaped_vals.append(defaults.get(col, "NULL"))

    # Keep original extra columns if any
    for col, val in col_to_val.items():
        if col not in required:
            shaped_cols.append(col)
            shaped_vals.append(val)

    new_sql = f"INSERT INTO students ({', '.join(shaped_cols)}) VALUES ({', '.join(shaped_vals)})"
    return new_sql, "added defaults for required student columns"


def _parse_write_shape(sql: str) -> tuple[str | None, str | None, str | None]:
    """Return (action, table, where_clause) for UPDATE/DELETE."""
    lowered = sql.strip().lower()
    if lowered.startswith("update"):
        match = re.match(
            r"\s*update\s+([a-zA-Z_][\w]*)\s+set\s+.+?\s+where\s+(.+)",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return "update", match.group(1), match.group(2).strip().rstrip(";")
    if lowered.startswith("delete"):
        match = re.match(
            r"\s*delete\s+from\s+([a-zA-Z_][\w]*)\s+where\s+(.+)",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return "delete", match.group(1), match.group(2).strip().rstrip(";")
    if lowered.startswith("insert"):
        match = re.match(r"\s*insert\s+into\s+([a-zA-Z_][\w]*)", sql, flags=re.IGNORECASE)
        if match:
            return "insert", match.group(1), None
    return None, None, None


def _format_samples(columns: list[str], rows: list[Sequence[Any]]) -> list[str]:
    samples: list[str] = []
    for row in rows:
        parts = [f"{col}={row[idx]}" for idx, col in enumerate(columns)]
        samples.append(", ".join(parts))
    return samples


def _collect_samples(ctx: AgentContext, table: str, where_clause: str | None, limit: int = 5) -> list[str]:
    if not where_clause:
        return []
    safe_where = where_clause.split(";")[0].strip()
    if not safe_where:
        return []
    sql = f"SELECT * FROM {table} WHERE {safe_where} LIMIT {limit}"
    try:
        cols, rows = ctx.db_handle.execute_select(sql)
        return _format_samples(cols, list(rows))
    except DbExecutionError:
        return []


def _requested_fields(question: str) -> set[str]:
    tokens = set(re.split(r"[^a-zA-Z0-9_]+", question.lower()))
    return {t for t in tokens if t in _KNOWN_FIELD_TOKENS}


def _ensure_requested_fields_present(sql: str, requested: set[str], available: set[str]) -> tuple[str | None, str | None]:
    if not requested:
        return sql, None
    missing = [f for f in requested if f not in available]
    if missing:
        return None, f"Requested fields not in schema: {', '.join(missing)}"
    # If projection is *, shape to include requested fields to ensure they appear in summary.
    if sql.strip().lower().startswith("select *") or re.search(r"select\\s+\\*\\s+from", sql, flags=re.IGNORECASE):
        proj = ", ".join(requested)
        sql = re.sub(r"select\\s+\\*\\s+from", f"SELECT {proj} FROM", sql, flags=re.IGNORECASE)
    return sql, None


def _llm_summarize(
    question: str,
    columns: list[str],
    rows: list[Sequence[Any]],
    model: Any,
    max_summary_tokens: int | None,
    budget: TokenBudget | None,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Return (summary, metrics, error_reason) using LLM, or (None, metrics, reason) on skip/fallback."""
    sample_limit = min(len(rows), 3)
    sample_rows = rows[:sample_limit]
    compact_rows = []
    for row in sample_rows:
        compact_rows.append({col: row[idx] for idx, col in enumerate(columns)})

    system_prompt = (
        "Provide a concise English answer to the user's question based on the provided rows. "
        "Keep it under two sentences. Do not repeat the SQL."
    )
    user_payload = {
        "question": question,
        "row_count": len(rows),
        "columns": columns,
        "sample_rows": compact_rows,
    }

    text = model.generate(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ]
    )
    metrics = _last_metrics(model)

    if budget:
        err = budget.record(metrics, "llm_summary")
        if err:
            return None, metrics, err

    if max_summary_tokens and metrics and metrics.get("total_tokens") and metrics["total_tokens"] > max_summary_tokens:
        return None, metrics, f"summary tokens {metrics['total_tokens']} exceed max {max_summary_tokens}"

    return text.strip(), metrics, None


def _action_from_sql(sql: str) -> str:
    lowered = sql.strip().lower()
    if lowered.startswith("insert"):
        return "insert"
    if lowered.startswith("delete"):
        return "delete"
    if lowered.startswith("update"):
        return "update"
    return "write"


def _selfcheck_sql(question: str, sql: str, model: Any | None) -> SelfCheckResult:
    if model is None:
        return SelfCheckResult(
            is_readonly=True,
            is_relevant=True,
            risk_level=SeverityLevel.INFO,
            notes="selfcheck disabled",
            passed=True,
        )

    payload = model.generate_json(
        [
            {
                "role": "system",
                "content": (
                    "Review the SQL for safety and relevance. Respond ONLY in JSON with fields: "
                    '{"pass": bool, "reason": "...", "fix_hint": "...", "confidence": 0-1, '
                    '"is_readonly": bool, "is_relevant": bool, "risk_level": "INFO"|"WARNING"|"DANGER"}.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"question": question, "sql": sql}),
            },
        ]
    )
    if not isinstance(payload, dict):
        payload = {}

    risk_level = str(payload.get("risk_level", SeverityLevel.WARNING)).upper()
    try:
        severity = SeverityLevel(risk_level)
    except ValueError:
        severity = SeverityLevel.WARNING

    reason = payload.get("reason") or payload.get("notes", "")
    fix_hint = payload.get("fix_hint") or ""
    confidence = payload.get("confidence")
    pass_flag = payload.get("pass")

    note_parts = []
    if reason:
        note_parts.append(str(reason))
    if fix_hint:
        note_parts.append(f"fix_hint: {fix_hint}")
    if confidence is not None:
        note_parts.append(f"confidence={confidence}")
    if pass_flag is not None:
        note_parts.append(f"pass={pass_flag}")
    notes = "; ".join(note_parts)

    return SelfCheckResult(
        is_readonly=bool(payload.get("is_readonly", False)),
        is_relevant=bool(payload.get("is_relevant", True)),
        risk_level=severity,
        notes=notes,
        passed=bool(pass_flag) if pass_flag is not None else True,
        reason=str(reason) if reason else None,
        fix_hint=str(fix_hint) if fix_hint else None,
        confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
    )


def repair_sql(question: str, sql: str, error_message: str, schema_snippet: str, model: Any) -> str | None:
    """Attempt a single-shot SQL repair via LLM JSON output."""
    payload = model.generate_json(
        [
            {
                "role": "system",
                "content": (
                    "You are fixing a SQL query that failed to execute. Return ONLY JSON: "
                    '{"sql": "...", "reason": "..."} with a corrected SELECT-only statement.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "failed_sql": sql,
                        "error": error_message,
                        "schema": schema_snippet,
                    }
                ),
            },
        ]
    )

    if not isinstance(payload, dict):
        return None

    new_sql = str(payload.get("sql", "")).strip()
    if not new_sql:
        return None

    text = new_sql
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
        text = text.replace("sql", "", 1).strip() if text.lower().startswith("sql") else text

    return text


def run_read_query(
    question: str,
    ctx: AgentContext,
    intent: IntentType,
    traces: list[StepTrace] | None = None,
    budget: TokenBudget | None = None,
    start_ts: float | None = None,
) -> TaskResult:
    traces = traces or []
    budget = budget or TokenBudget(
        max_step_tokens=ctx.config.max_prompt_tokens,
        max_total_tokens=ctx.config.max_total_tokens,
    )
    start_ts = start_ts or time.perf_counter()

    full_schema = ctx.db_handle.get_table_info()
    available_cols = _parse_schema_columns(full_schema)
    max_cols = 3 if intent == IntentType.READ_SIMPLE else 5
    schema_snippet = select_schema_subset(question, full_schema, ctx.config.top_k, max_columns=max_cols)
    traces.append(StepTrace(name="load_schema", output_preview=_preview(schema_snippet)))

    attempted_strict = False
    while True:
        if ctx.config.max_wall_time_ms and (time.perf_counter() - start_ts) * 1000 > ctx.config.max_wall_time_ms:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message="Time limit exceeded during planning.",
                error_code="TIMEOUT",
                hint="Simplify the question or increase SQL_AGENT_MAX_WALL_MS.",
                raw_question=question,
                trace=traces,
            )
        gen = _generate_sql_with_llm(
            question,
            schema_snippet,
            ctx.sql_model,
            ctx.config.top_k,
            strict=attempted_strict,
        )
        if not gen:
            return TaskResult(
                intent=intent,
                status=TaskStatus.UNSUPPORTED,
                query_result=None,
                error_message="Model refused to generate a read-only SQL query.",
                raw_question=question,
                trace=traces,
            )
        shaped_sql, shape_note = _shape_sql(gen.sql, question, ctx.config.sql_default_limit)
        if shape_note:
            traces.append(StepTrace(name="shape_sql", output_preview=_preview(shaped_sql), notes=shape_note))
        gen.sql = shaped_sql

        # Ensure requested fields are projected when schema supports them
        requested = _requested_fields(question)
        enforced_sql, missing_reason = _ensure_requested_fields_present(gen.sql, requested, available_cols)
        if missing_reason:
            return TaskResult(
                intent=intent,
                status=TaskStatus.UNSUPPORTED,
                query_result=None,
                error_message=missing_reason,
                error_code="SCHEMA_MISSING_COLUMN",
                hint="Try available columns from schema hints.",
                raw_question=question,
                trace=traces,
            )
        if enforced_sql and enforced_sql != gen.sql:
            gen.sql = enforced_sql
            traces.append(
                StepTrace(
                    name="shape_projection",
                    output_preview=_preview(gen.sql),
                    notes="ensured requested fields",
                )
            )
        gen_metrics = _last_metrics(ctx.sql_model)
        traces.append(
            StepTrace(
                name="generate_sql",
                output_preview=_preview(gen.sql),
                **_metric_fields(gen_metrics),
            )
        )
        err = budget.record(gen_metrics, "generate_sql")
        if err:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message=err,
                raw_question=question,
                trace=traces,
        )

        wants_instructor = any(word in question.lower() for word in ("instructor", "teacher", "professor"))
        schema_has_instructor = _schema_has_column(full_schema, "instructor")
        fabricated_instructor = (
            wants_instructor and schema_has_instructor and _has_constant_projection(gen.sql, "instructor")
        )
        if fabricated_instructor:
            traces.append(
                StepTrace(
                    name="faithfulness_check",
                    output_preview="constant projection to instructor detected; retrying with strict schema",
                    severity=SeverityLevel.WARNING,
                )
            )
            if attempted_strict:
                return TaskResult(
                    intent=intent,
                    status=TaskStatus.ERROR,
                    query_result=None,
                    error_message="SQL appears to fabricate instructor values.",
                    raw_question=question,
                    trace=traces,
                )
            attempted_strict = True
            continue
        break

    sc: SelfCheckResult
    if ctx.config.selfcheck_enabled:
        sc = _selfcheck_sql(question, gen.sql, ctx.sql_model)
        traces.append(
            StepTrace(
                name="selfcheck",
                output_preview=_preview(
                    f"is_readonly={sc.is_readonly}, is_relevant={sc.is_relevant}, risk_level={sc.risk_level}"
                ),
                severity=sc.risk_level,
                notes=sc.notes or None,
                **_metric_fields(_last_metrics(ctx.sql_model)),
            )
        )
        err = budget.record(_last_metrics(ctx.sql_model), "selfcheck")
        if err:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message=err,
                raw_question=question,
                trace=traces,
            )
    else:
        sc = SelfCheckResult(
            is_readonly=True,
            is_relevant=True,
            risk_level=SeverityLevel.INFO,
            notes="selfcheck disabled",
            passed=True,
        )

    if ctx.config.selfcheck_enabled and not sc.passed:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message=sc.reason or sc.notes or "SQL failed selfcheck.",
            raw_question=question,
            trace=traces,
        )

    validate_readonly_sql(gen.sql)

    try:
        columns, all_rows = ctx.db_handle.execute_select(gen.sql)
    except DbExecutionError as exc:
        repair_sql_text = repair_sql(question, gen.sql, exc.inner_message, schema_snippet, ctx.sql_model)
        if not repair_sql_text:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message="Failed to repair SQL.",
                raw_question=question,
                trace=traces,
            )

        validate_readonly_sql(repair_sql_text)
        traces.append(
            StepTrace(
                name="repair_sql",
                output_preview=_preview(repair_sql_text),
                **_metric_fields(_last_metrics(ctx.sql_model)),
            )
        )
        err = budget.record(_last_metrics(ctx.sql_model), "repair_sql")
        if err:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message=err,
                raw_question=question,
                trace=traces,
            )

        if ctx.config.selfcheck_enabled:
            sc2 = _selfcheck_sql(question, repair_sql_text, ctx.sql_model)
            traces.append(
                StepTrace(
                    name="selfcheck_after_repair",
                    output_preview=_preview(
                        f"is_readonly={sc2.is_readonly}, is_relevant={sc2.is_relevant}, risk_level={sc2.risk_level}"
                    ),
                    severity=sc2.risk_level,
                    notes=sc2.notes or None,
                    **_metric_fields(_last_metrics(ctx.sql_model)),
                )
            )
            err = budget.record(_last_metrics(ctx.sql_model), "selfcheck_after_repair")
            if err:
                return TaskResult(
                    intent=intent,
                    status=TaskStatus.ERROR,
                    query_result=None,
                    error_message=err,
                    raw_question=question,
                    trace=traces,
                )
            if not sc2.passed:
                return TaskResult(
                    intent=intent,
                    status=TaskStatus.UNSUPPORTED,
                    query_result=None,
                    error_message=sc2.reason or sc2.notes or "SQL failed selfcheck after repair.",
                    raw_question=question,
                    trace=traces,
                )
        try:
            columns, all_rows = ctx.db_handle.execute_select(repair_sql_text)
            gen.sql = repair_sql_text
        except DbExecutionError:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message="Failed to execute repaired SQL.",
                raw_question=question,
                trace=traces,
            )

    result_cols_lower = [c.lower() for c in columns]
    missing_requested = [field for field in requested if field not in result_cols_lower]
    if missing_requested:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message=f"Result missing requested fields: {', '.join(missing_requested)}",
            error_code="FIELDS_MISSING",
            hint="Try asking for those columns explicitly.",
            raw_question=question,
            trace=traces,
        )

    row_count = len(all_rows)
    max_rows = ctx.config.max_rows or 20
    rows = all_rows[:max_rows]
    traces.append(StepTrace(name="execute_sql", output_preview=f"row_count={row_count}"))

    use_llm_summary = (
        ctx.config.allow_llm_summary
        and row_count <= ctx.config.max_summary_rows
        and _needs_llm_summary(question)
    )

    summary = summarize(question, columns, rows)
    if use_llm_summary:
        llm_summary, metrics, reason = _llm_summarize(
            question,
            list(columns),
            list(rows),
            ctx.sql_model,
            ctx.config.max_summary_tokens,
            budget,
        )
        if llm_summary:
            summary = llm_summary
        traces.append(
            StepTrace(
                name="summarize",
                output_preview=_preview(summary if llm_summary else f"llm fallback -> {summary}"),
                **_metric_fields(metrics),
                notes=reason,
            )
        )
    else:
        skip_reason = None
        if row_count > ctx.config.max_summary_rows:
            skip_reason = f"skipped llm summary (row_count={row_count} > max={ctx.config.max_summary_rows})"
        traces.append(
            StepTrace(
                name="summarize",
                output_preview=_preview(summary),
                notes=skip_reason,
            )
        )

    return TaskResult(
        intent=intent,
        status=TaskStatus.SUCCESS,
        query_result=QueryResult(
            sql=gen.sql,
            columns=list(columns),
            rows=list(rows),
            summary=summary,
            trace=traces if ctx.config.allow_trace else None,
        ),
        error_message=None,
        raw_question=question,
        trace=traces,
    )


def run_write_query(
    question: str,
    ctx: AgentContext,
    intent: IntentType,
    traces: list[StepTrace] | None = None,
    budget: TokenBudget | None = None,
    dry_run: bool | None = None,
    force: bool = False,
    apply_changes: bool = False,
    start_ts: float | None = None,
) -> TaskResult:
    traces = traces or []
    budget = budget or TokenBudget(
        max_step_tokens=ctx.config.max_prompt_tokens,
        max_total_tokens=ctx.config.max_total_tokens,
    )
    start_ts = start_ts or time.perf_counter()

    if not ctx.config.allow_write:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message="Write operations are disabled. Use --allow-write to enable.",
            error_code="WRITE_DISABLED",
            hint="Run with --allow-write or set SQL_AGENT_ALLOW_WRITE=1",
            raw_question=question,
            trace=traces,
        )

    if force and not ctx.config.allow_force:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message="Force execution is not allowed.",
            error_code="FORCE_DISABLED",
            hint="Set SQL_AGENT_ALLOW_FORCE=1 to permit --force.",
            raw_question=question,
            trace=traces,
        )

    full_schema = ctx.db_handle.get_table_info()
    schema_snippet = select_schema_subset(question, full_schema, ctx.config.top_k, max_columns=5)
    traces.append(StepTrace(name="load_schema", output_preview=_preview(schema_snippet)))

    gen = _generate_write_sql(question, schema_snippet, ctx.sql_model, ctx.config.top_k)
    if not gen:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message="Model refused to generate a write SQL statement.",
            error_code="WRITE_REFUSED",
            raw_question=question,
            trace=traces,
        )

    shape_note = None
    if "insert into students" in gen.sql.lower():
        gen.sql, shape_note = _shape_student_insert(gen.sql)

    gen_metrics = _last_metrics(ctx.sql_model)
    traces.append(
        StepTrace(
            name="generate_write_sql",
            output_preview=_preview(gen.sql),
            **_metric_fields(gen_metrics),
            notes=shape_note,
        )
    )
    if ctx.config.max_wall_time_ms and (time.perf_counter() - start_ts) * 1000 > ctx.config.max_wall_time_ms:
        return TaskResult(
            intent=intent,
            status=TaskStatus.ERROR,
            query_result=None,
            error_message="Time limit exceeded during planning.",
            error_code="TIMEOUT",
            hint="Try a simpler request or raise SQL_AGENT_MAX_WALL_MS.",
            raw_question=question,
            trace=traces,
        )
    err = budget.record(gen_metrics, "generate_write_sql")
    if err:
        return TaskResult(
            intent=intent,
            status=TaskStatus.ERROR,
            query_result=None,
            error_message=err,
            raw_question=question,
            trace=traces,
        )

    require_where = ctx.config.require_where and not (force and ctx.config.allow_force)
    try:
        validate_write_sql(gen.sql, require_where=require_where)
    except SqlGuardViolation as exc:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message=exc.reason,
            error_code="WRITE_GUARD",
            hint="Narrow WHERE or remove dangerous keywords.",
            raw_question=question,
            trace=traces,
        )

    action, table, where_clause = _parse_write_shape(gen.sql)
    user_dry_run = ctx.config.dry_run_default if dry_run is None else dry_run
    probe_affected: int | None = None
    last_row_id: int | None = None
    samples_before: list[str] = []

    if action in ("update", "delete"):
        try:
            probe_affected, _ = ctx.db_handle.execute_write(gen.sql, dry_run=True, require_where=require_where)
            traces.append(
                StepTrace(
                    name="execute_write_probe",
                    output_preview=f"affected_rows={probe_affected}, dry_run=True",
                )
            )
        except DbExecutionError as exc:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message=exc.inner_message,
                error_code="WRITE_EXEC_ERROR",
                raw_question=question,
                trace=traces,
            )
        if ctx.config.max_wall_time_ms and (time.perf_counter() - start_ts) * 1000 > ctx.config.max_wall_time_ms:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message="Time limit exceeded during probe.",
                error_code="TIMEOUT",
                hint="Narrow the write or raise SQL_AGENT_MAX_WALL_MS.",
                raw_question=question,
                trace=traces,
            )
        samples_before = _collect_samples(ctx, table or "", where_clause) if table else []
        if probe_affected is not None and probe_affected > ctx.config.max_write_rows:
            return TaskResult(
                intent=intent,
                status=TaskStatus.UNSUPPORTED,
                query_result=None,
                error_message=f"Would affect {probe_affected} rows; limit is {ctx.config.max_write_rows}.",
                error_code="WRITE_TOO_LARGE",
                hint="Add stricter WHERE or LIMIT rows.",
                raw_question=question,
                trace=traces,
            )
        if probe_affected is not None and probe_affected > 1 and not force:
            return TaskResult(
                intent=intent,
                status=TaskStatus.UNSUPPORTED,
                query_result=None,
                error_message=f"Wide update/delete would affect {probe_affected} rows; use --force or narrow WHERE.",
                error_code="WRITE_WIDE",
                hint="Add stricter WHERE or use --force if intentional.",
                raw_question=question,
                trace=traces,
            )
    elif action == "insert":
        try:
            probe_affected, last_row_id = ctx.db_handle.execute_write(gen.sql, dry_run=True, require_where=require_where)
            traces.append(
                StepTrace(
                    name="execute_write_probe",
                    output_preview=f"affected_rows={probe_affected}, dry_run=True",
                )
            )
        except DbExecutionError as exc:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message=exc.inner_message,
                error_code="WRITE_EXEC_ERROR",
                raw_question=question,
                trace=traces,
            )

    # Require explicit confirmation to commit
    if ctx.config.write_apply_required and not apply_changes:
        summary_parts = [f"Planned {action or 'write'}"]
        if probe_affected is not None:
            summary_parts.append(f"rows={probe_affected}")
        if where_clause:
            summary_parts.append(f"where={where_clause}")
        if samples_before:
            summary_parts.append(f"sample_before={'; '.join(samples_before[:3])}")
        summary = "; ".join(summary_parts)
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=QueryResult(
                sql=gen.sql,
                columns=[],
                rows=[],
                summary=summary,
                trace=traces if ctx.config.allow_trace else None,
            ),
            error_message="Write requires confirmation.",
            error_code="WRITE_CONFIRM_REQUIRED",
            hint="Re-run with --apply (and --allow-write) to commit.",
            raw_question=question,
            trace=traces,
        )

    final_dry_run = user_dry_run
    if apply_changes:
        final_dry_run = False

    try:
        affected, last_row_id = ctx.db_handle.execute_write(
            gen.sql,
            dry_run=final_dry_run,
            require_where=require_where,
        )
    except DbExecutionError as exc:
        return TaskResult(
            intent=intent,
            status=TaskStatus.ERROR,
            query_result=None,
            error_message=exc.inner_message,
            error_code="WRITE_EXEC_ERROR",
            raw_question=question,
            trace=traces,
        )
    if ctx.config.max_wall_time_ms and (time.perf_counter() - start_ts) * 1000 > ctx.config.max_wall_time_ms:
        return TaskResult(
            intent=intent,
            status=TaskStatus.ERROR,
            query_result=None,
            error_message="Time limit exceeded during execution.",
            error_code="TIMEOUT",
            hint="Reduce result size or raise SQL_AGENT_MAX_WALL_MS.",
            raw_question=question,
            trace=traces,
        )

    traces.append(
        StepTrace(
            name="execute_write",
            output_preview=f"affected_rows={affected}, dry_run={final_dry_run}",
            severity=SeverityLevel.WARNING
            if (affected > 1 and not final_dry_run and action in ("update", "delete"))
            else SeverityLevel.INFO,
            notes="multi-row commit with force" if (affected > 1 and not final_dry_run and force) else None,
        )
    )

    if (
        not final_dry_run
        and probe_affected is not None
        and action in ("update", "delete")
        and affected != probe_affected
        and not force
    ):
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message=f"Plan/apply mismatch: estimated {probe_affected}, actual {affected}.",
            error_code="WRITE_DIVERGED",
            hint="Re-run after narrowing WHERE or use --force if intentional.",
            raw_question=question,
            trace=traces,
        )

    samples_after: list[str] = []
    if not final_dry_run:
        if action in ("update", "delete"):
            samples_after = _collect_samples(ctx, table or "", where_clause) if table else []
        elif action == "insert" and table:
            if last_row_id:
                samples_after = _collect_samples(ctx, table, f"rowid = {last_row_id}")
            else:
                samples_after = _collect_samples(ctx, table, "1=1")

    def _evidence_part(label: str, samples: list[str]) -> str | None:
        if not samples:
            return None
        shown = samples[:3]
        more = f" (+{len(samples) - len(shown)} more)" if len(samples) > len(shown) else ""
        return f"{label}: {'; '.join(shown)}{more}"

    evidence_parts: list[str] = []
    if where_clause:
        evidence_parts.append(f"where={where_clause}")
    if samples_before:
        evidence = _evidence_part("before", samples_before)
        if evidence:
            evidence_parts.append(evidence)
    if samples_after:
        evidence = _evidence_part("after", samples_after)
        if evidence:
            evidence_parts.append(evidence)
    if samples_before or samples_after:
        traces.append(
            StepTrace(
                name="evidence",
                output_preview="; ".join(evidence_parts) if evidence_parts else None,
            )
        )

    action_label = action or _action_from_sql(gen.sql)
    if action_label == "delete":
        summary = f"{'Dry-run' if final_dry_run else 'Deleted'} {affected} row(s)"
    elif action_label == "update":
        summary = f"{'Dry-run' if final_dry_run else 'Updated'} {affected} row(s)"
    else:
        state = "Dry-run" if final_dry_run else "Committed"
        summary = f"{state}: {affected} row(s) affected"
        if last_row_id and affected > 0 and not final_dry_run:
            summary = f"{summary}; last_row_id={last_row_id}"

    if evidence_parts:
        summary = f"{summary} [{'; '.join(evidence_parts)}]"

    return TaskResult(
        intent=intent,
        status=TaskStatus.SUCCESS,
        query_result=QueryResult(
            sql=gen.sql,
            columns=[],
            rows=[],
            summary=summary,
            trace=traces if ctx.config.allow_trace else None,
        ),
        error_message=None,
        raw_question=question,
        trace=traces,
    )


def run_task(
    question: str,
    ctx: AgentContext,
    *,
    dry_run_override: bool | None = None,
    force: bool = False,
    apply_changes: bool = False,
) -> TaskResult:
    traces: list[StepTrace] = []
    budget = TokenBudget(
        max_step_tokens=ctx.config.max_prompt_tokens,
        max_total_tokens=ctx.config.max_total_tokens,
    )
    start_ts = time.perf_counter()

    intent = detect_intent(question, ctx.intent_model)
    intent_metrics = _last_metrics(ctx.intent_model)
    traces.append(
        StepTrace(
            name="intent_detection",
            input_preview=_preview(question),
            output_preview=intent.value,
            **_metric_fields(intent_metrics),
        )
    )
    err = budget.record(intent_metrics, "intent_detection")
    if err:
        return TaskResult(
            intent=intent,
            status=TaskStatus.ERROR,
            query_result=None,
            error_message=err,
            raw_question=question,
            trace=traces,
        )

    if intent in (IntentType.READ_SIMPLE, IntentType.READ_ANALYTIC):
        return run_read_query(question, ctx, intent, traces, budget, start_ts=start_ts)

    if intent == IntentType.WRITE:
        return run_write_query(
            question,
            ctx,
            intent,
            traces,
            budget,
            dry_run=dry_run_override,
            force=force,
            apply_changes=apply_changes,
            start_ts=start_ts,
        )

    return TaskResult(
        intent=intent,
        status=TaskStatus.UNSUPPORTED,
        query_result=None,
        error_message="Only read/write database questions are supported in this demo.",
        raw_question=question,
        trace=traces,
    )


__all__ = [
    "SqlGenerationResult",
    "select_schema_subset",
    "_generate_sql_with_llm",
    "_generate_write_sql",
    "_selfcheck_sql",
    "repair_sql",
    "run_read_query",
    "run_write_query",
    "run_task",
]
