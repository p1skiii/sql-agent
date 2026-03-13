"""SQL agent pipelines for read-only queries."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
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
    question: str, schema_snippet: str, model: Any, top_k: int, dialect: str, strict: bool = False
) -> SqlGenerationResult | None:
    system_prompt = (
        f"You are an expert SQL assistant. Generate a single {dialect}-compatible SQL query that answers the user's question. "
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
    question: str, schema_snippet: str, model: Any, top_k: int, dialect: str
) -> SqlGenerationResult | None:
    system_prompt = (
        f"You are an expert SQL assistant. Generate ONE safe {dialect}-compatible data-modifying statement (INSERT, UPDATE, or DELETE). "
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


def _quote_table_identifiers(sql: str) -> str:
    """Quote table names that contain hyphens or start with digits to avoid SQLite syntax errors."""
    def repl(match):
        name = match.group(1)
        stripped = name.strip()
        if stripped.startswith(("\"", "`", "[")):
            return match.group(0)  # already quoted
        if any(ch in stripped for ch in "- ") or stripped[:1].isdigit():
            return match.group(0).replace(name, f'"{stripped}"', 1)
        return match.group(0)

    sql = re.sub(r"(?i)from\\s+([\\w\\-\\.]+)", repl, sql)
    sql = re.sub(r"(?i)join\\s+([\\w\\-\\.]+)", repl, sql)
    return sql


def _quote_column_identifiers(sql: str) -> str:
    """
    Quote column identifiers that contain spaces, slashes, dashes or start with digits.
    Applies in SELECT list and common clauses (WHERE/GROUP/ORDER/HAVING/UNION).
    """
    def quote_ident(ident: str) -> str:
        ident = ident.strip()
        if not ident:
            return ident
        if ident.startswith(("\"", "`", "[")):
            return ident
        if any(ch in ident for ch in (" ", "-", "/", "\\")) or ident[:1].isdigit():
            return f'"{ident}"'
        return ident

    # Quote table names in FROM/JOIN clauses when they include special chars
    def repl_table(match):
        table = match.group(2)
        alias = match.group(3) or ""
        if table.startswith("("):
            return match.group(0)
        return f"{match.group(1)} {quote_ident(table)}{alias}"

    sql = re.sub(r"(?i)\b(from|join)\s+([`\"\[]?[\w.\-/]+[`\"\]]?)(\s+(?:as\s+)?[\w]+)?",
                 repl_table, sql)

    # Quote columns in SELECT list
    def repl_select(match):
        cols = match.group(1)
        parts = []
        for part in cols.split(","):
            if " as " in part.lower():
                left, right = re.split("(?i)\\s+as\\s+", part, maxsplit=1)
                parts.append(f"{quote_ident(left)} AS {quote_ident(right)}")
            else:
                parts.append(quote_ident(part))
        return "SELECT " + ", ".join(parts) + " FROM"

    sql = re.sub(r"(?is)select\\s+(.*?)\\s+from", repl_select, sql, count=1)

    # Quote simple WHERE/GROUP/ORDER/HAVING column patterns
    def repl_clause(match):
        col = quote_ident(match.group(1))
        op = match.group(2)
        rest = match.group(3)
        return f" {col} {op}{rest}"
    sql = re.sub(r"(\s)([\w.\-/]+)\s*(=|>|<|>=|<=|!=|like|in|between)(\s)",
                 lambda m: f"{m.group(1)}{quote_ident(m.group(2))} {m.group(3)}{m.group(4)}",
                 sql, flags=re.IGNORECASE)
    sql = re.sub(r"(?i)(group by|order by|having)\s+([\w.\-/, ]+)",
                 lambda m: m.group(1) + " " + ", ".join(quote_ident(p) for p in m.group(2).split(",")), sql)

    return sql


def _apply_sqlite_compat_rewrite(sql: str) -> str:
    sql = re.sub(r"(?i)year\(([^)]+)\)", r"strftime('%Y', \1)", sql)
    sql = re.sub(r"(?i)month\(([^)]+)\)", r"strftime('%m', \1)", sql)
    sql = re.sub(r"(?i)date_format\(([^,]+),\s*'%%Y-%%m-%%d'\)", r"date(\1)", sql)
    return sql


def _backend_sql_dialect(db_backend: str) -> str:
    return "PostgreSQL" if str(db_backend).lower() == "postgres" else "SQLite"


def _rewrite_sql_for_backend(sql: str, db_backend: str) -> str:
    if str(db_backend).lower() == "sqlite":
        return _apply_sqlite_compat_rewrite(sql)
    return sql


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
        "请基于提供的查询结果，用简洁自然的中文回答用户问题。"
        "控制在两句话以内，不要重复 SQL，不要写成机械摘要。"
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


def repair_sql(
    question: str,
    sql: str,
    error_message: str,
    schema_snippet: str,
    model: Any,
    dialect: str,
) -> str | None:
    """Attempt a single-shot SQL repair via LLM JSON output."""
    payload = model.generate_json(
        [
            {
                "role": "system",
                "content": (
                    "You are fixing a SQL query that failed to execute. Return ONLY JSON: "
                    '{"sql": "...", "reason": "..."} with a corrected '
                    f"{dialect}-compatible SELECT-only statement."
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
) -> TaskResult:
    traces = traces or []
    budget = budget or TokenBudget(
        max_step_tokens=ctx.config.max_prompt_tokens,
        max_total_tokens=ctx.config.max_total_tokens,
    )

    full_schema = ctx.db_handle.get_table_info()
    max_cols = 3 if intent == IntentType.READ_SIMPLE else 5
    if ctx.config.schema_mode == "full":
        schema_snippet = full_schema
        limit = ctx.config.schema_truncate_chars or 12000
        if len(schema_snippet) > limit:
            schema_snippet = schema_snippet[:limit]
            traces.append(StepTrace(name="schema_truncate", output_preview=f"full_schema truncated to {limit} chars"))
    else:
        schema_snippet = select_schema_subset(question, full_schema, ctx.config.top_k, max_columns=max_cols)
    traces.append(StepTrace(name="load_schema", output_preview=_preview(schema_snippet)))
    traces.append(StepTrace(name="guard_config", output_preview=f"guard_level={ctx.config.guard_level}"))

    attempted_strict = False
    while True:
        gen = _generate_sql_with_llm(
            question,
            schema_snippet,
            ctx.sql_model,
            ctx.config.top_k,
            _backend_sql_dialect(ctx.config.db_backend),
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
        raw_sql = gen.sql
        gen.sql = _quote_table_identifiers(gen.sql)
        gen.sql = _quote_column_identifiers(gen.sql)
        gen.sql = _rewrite_sql_for_backend(gen.sql, ctx.config.db_backend)
        shaped_sql, shape_note = _shape_sql(gen.sql, question, ctx.config.sql_default_limit)
        if shape_note:
            traces.append(StepTrace(name="shape_sql", output_preview=_preview(shaped_sql), notes=shape_note))
        gen.sql = shaped_sql
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

    validate_readonly_sql(gen.sql, guard_level=ctx.config.guard_level)

    try:
        columns, all_rows = ctx.db_handle.execute_select(gen.sql)
    except DbExecutionError as exc:
        if not ctx.config.allow_repair:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message=exc.inner_message,
                raw_question=question,
                trace=traces,
            )
        repair_sql_text = repair_sql(
            question,
            gen.sql,
            exc.inner_message,
            schema_snippet,
            ctx.sql_model,
            _backend_sql_dialect(ctx.config.db_backend),
        )
        if not repair_sql_text:
            return TaskResult(
                intent=intent,
                status=TaskStatus.ERROR,
                query_result=None,
                error_message="Failed to repair SQL.",
                raw_question=question,
                trace=traces,
            )

        validate_readonly_sql(repair_sql_text, guard_level=ctx.config.guard_level)
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
                query_result=QueryResult(
                    sql=repair_sql_text,
                    raw_sql=raw_sql,
                    repaired_sql=repair_sql_text,
                    row_count=0,
                    columns=[],
                    rows=[],
                    summary="",
                    trace=traces if ctx.config.allow_trace else None,
                ),
                error_message="Failed to execute repaired SQL.",
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
            raw_sql=raw_sql,
            repaired_sql=gen.sql if gen.sql != raw_sql else None,
            row_count=row_count,
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
) -> TaskResult:
    traces = traces or []
    budget = budget or TokenBudget(
        max_step_tokens=ctx.config.max_prompt_tokens,
        max_total_tokens=ctx.config.max_total_tokens,
    )

    if not ctx.config.allow_write:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message="Write operations are disabled. Use --allow-write to enable.",
            raw_question=question,
            trace=traces,
        )

    if force and not ctx.config.allow_force:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message="Force execution is not allowed.",
            raw_question=question,
            trace=traces,
        )

    full_schema = ctx.db_handle.get_table_info()
    if ctx.config.schema_mode == "full":
        schema_snippet = full_schema
        if len(schema_snippet) > 12000:
            schema_snippet = schema_snippet[:12000]
            traces.append(StepTrace(name="schema_truncate", output_preview="full_schema truncated to 12000 chars"))
    else:
        schema_snippet = select_schema_subset(question, full_schema, ctx.config.top_k, max_columns=5)
    traces.append(StepTrace(name="load_schema", output_preview=_preview(schema_snippet)))
    traces.append(StepTrace(name="guard_config", output_preview=f"guard_level={ctx.config.guard_level} require_where={ctx.config.require_where}")) 

    gen = _generate_write_sql(
        question,
        schema_snippet,
        ctx.sql_model,
        ctx.config.top_k,
        _backend_sql_dialect(ctx.config.db_backend),
    )
    if not gen:
        return TaskResult(
            intent=intent,
            status=TaskStatus.UNSUPPORTED,
            query_result=None,
            error_message="Model refused to generate a write SQL statement.",
            raw_question=question,
            trace=traces,
        )

    shape_note = None
    gen.sql = _quote_table_identifiers(gen.sql)
    gen.sql = _quote_column_identifiers(gen.sql)
    gen.sql = _rewrite_sql_for_backend(gen.sql, ctx.config.db_backend)
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
            raw_question=question,
            trace=traces,
        )

    user_dry_run = ctx.config.dry_run_default if dry_run is None else dry_run
    is_update_or_delete = gen.sql.strip().lower().startswith(("update", "delete"))

    # Attempt to derive a SELECT statement to track before/after states
    returning_sql = None
    if is_update_or_delete:
        m_update = re.match(r"(?i)\s*update\s+([a-zA-Z0-9_\-\"\'\`\[\]]+)\s+set\s+(.*?)\s+(where\s+.*)", gen.sql)
        m_delete = re.match(r"(?i)\s*delete\s+from\s+([a-zA-Z0-9_\-\"\'\`\[\]]+)\s+(where\s+.*)", gen.sql)
        if m_update:
            returning_sql = f"SELECT * FROM {m_update.group(1)} {m_update.group(3)}"
        elif m_delete:
            returning_sql = f"SELECT * FROM {m_delete.group(1)} {m_delete.group(2)}"

    before_columns, before_rows = [], []
    after_columns, after_rows = [], []

    if returning_sql:
        try:
            b_cols, b_rows = ctx.db_handle.execute_select(returning_sql)
            before_columns = list(b_cols)
            before_rows = list(b_rows)
        except Exception:
            pass

    # Probe updates/deletes to detect wide impact unless guard is off
    probe_affected = None
    if is_update_or_delete and ctx.config.guard_level != "off":
        try:
            probe_affected, _, _, _ = ctx.db_handle.execute_write(
                gen.sql,
                dry_run=True,
                require_where=require_where,
            )
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
                raw_question=question,
                trace=traces,
            )
        if probe_affected is not None and probe_affected > 1 and not force:
            return TaskResult(
                intent=intent,
                status=TaskStatus.UNSUPPORTED,
                query_result=None,
                error_message=f"Wide update/delete would affect {probe_affected} rows; use --force or narrow WHERE.",
                raw_question=question,
                trace=traces,
            )

    final_dry_run = user_dry_run

    try:
        affected, last_row_id, r_cols, r_rows = ctx.db_handle.execute_write(
            gen.sql,
            dry_run=final_dry_run,
            require_where=require_where,
            returning_sql=returning_sql,
        )
        if r_cols is not None and r_rows is not None:
            after_columns = list(r_cols)
            after_rows = list(r_rows)
    except DbExecutionError as exc:
        return TaskResult(
            intent=intent,
            status=TaskStatus.ERROR,
            query_result=None,
            error_message=exc.inner_message,
            raw_question=question,
            trace=traces,
        )

    traces.append(
        StepTrace(
            name="execute_write",
            output_preview=f"affected_rows={affected}, dry_run={final_dry_run}",
            severity=SeverityLevel.WARNING
            if (affected > 1 and not final_dry_run and is_update_or_delete)
            else SeverityLevel.INFO,
            notes="multi-row commit with force" if (affected > 1 and not final_dry_run and force) else None,
        )
    )

    action = _action_from_sql(gen.sql)
    if action == "delete":
        if final_dry_run:
            summary = f"演练模式：将删除 {affected} 条记录"
        else:
            summary = f"已删除 {affected} 条记录"
    elif action == "update":
        if final_dry_run:
            summary = f"演练模式：将更新 {affected} 条记录"
        else:
            summary = f"已更新 {affected} 条记录"
    else:
        state = "演练模式" if final_dry_run else "已提交"
        summary = f"{state}：影响了 {affected} 条记录"
        if last_row_id and affected > 0:
            summary = f"{summary}; last_row_id={last_row_id}"
    if probe_affected is not None and final_dry_run and probe_affected != affected:
        summary = f"{summary}（预估影响 {probe_affected} 条）"

    return TaskResult(
        intent=intent,
        status=TaskStatus.SUCCESS,
        query_result=QueryResult(
            sql=gen.sql,
            row_count=affected,
            columns=after_columns,
            rows=after_rows,
            before_columns=before_columns,
            before_rows=before_rows,
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
) -> TaskResult:
    traces: list[StepTrace] = []
    budget = TokenBudget(
        max_step_tokens=ctx.config.max_prompt_tokens,
        max_total_tokens=ctx.config.max_total_tokens,
    )

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
        return run_read_query(question, ctx, intent, traces, budget)

    if intent == IntentType.WRITE:
        return run_write_query(
            question,
            ctx,
            intent,
            traces,
            budget,
            dry_run=dry_run_override,
            force=force,
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
