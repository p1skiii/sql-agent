"""Result summarization helpers."""
from __future__ import annotations

import re
from typing import Sequence

_PREVIEW_LIMIT = 10
_STOP_TOKENS = {
    "with",
    "where",
    "who",
    "whose",
    "that",
    "which",
    "from",
    "by",
    "for",
    "in",
    "on",
    "to",
    "of",
    "and",
}
_LIST_TRIGGERS = ("list", "show", "display", "return", "give me", "find")


def _tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]


def _extract_subject(question: str) -> str | None:
    """Pull a lightweight subject phrase from list-style questions."""
    q = question.lower().replace("?", " ")
    for trigger in _LIST_TRIGGERS:
        idx = q.find(trigger)
        if idx == -1:
            continue

        remainder = q[idx + len(trigger) :].strip()
        remainder = re.sub(r"^(all|the|any|please)\s+", "", remainder)

        tokens = _tokenize(remainder)
        subject_tokens: list[str] = []
        for token in tokens:
            if token in _STOP_TOKENS:
                break
            subject_tokens.append(token)
            if len(subject_tokens) >= 3:
                break

        if subject_tokens:
            return " ".join(subject_tokens)
    return None


def _pick_display_column(question: str, columns: list[str]) -> int | None:
    """Choose the column that best answers the question (favoring names)."""
    question_tokens = set(_tokenize(question))
    best_idx: int | None = None
    best_score = 0

    for idx, col in enumerate(columns):
        col_tokens = set(_tokenize(col))
        score = 0
        if "name" in col.lower():
            score += 5
        score += len(question_tokens & col_tokens)
        if len(columns) == 1:
            score += 1  # single-column tables should be used directly

        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx is None:
        return None

    if best_score == 0 and len(columns) > 1:
        return None

    return best_idx


def _label_for_count(label: str, count: int) -> str:
    """Return a short, count-aware label (e.g., '1 student', '3 students')."""
    cleaned = label.strip()
    if not cleaned:
        return "result" if count == 1 else "results"

    words = cleaned.split()
    head, tail = words[:-1], words[-1]

    def singular(word: str) -> str:
        if word.endswith("ss"):
            return word
        if word.endswith("s"):
            return word[:-1]
        return word

    def plural(word: str) -> str:
        if word.endswith("s"):
            return word
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return f"{word[:-1]}ies"
        return f"{word}s"

    chosen = singular(tail) if count == 1 else plural(tail)
    if head:
        return " ".join([*head, chosen])
    return chosen


def _stringify(value: object) -> str:
    return "None" if value is None else str(value)


def _format_preview(values: list[str], total_count: int) -> str:
    preview = ", ".join(values)
    extra = total_count - len(values)
    if extra > 0:
        return f"{preview}，另外还有 {extra} 个"
    return preview


def _format_row(columns: list[str], row: Sequence[object]) -> str:
    pairs = [f"{col}={_stringify(val)}" for col, val in zip(columns, row)]
    return ", ".join(pairs)


def _zh_count_phrase(label_source: str, row_count: int) -> str:
    lowered = label_source.lower().strip()
    if "student name" in lowered:
        return f"{row_count} 个学生姓名"
    if lowered in {"name", "names"} or " name" in lowered:
        return f"{row_count} 个名字"
    if "student" in lowered:
        return f"{row_count} 名学生"
    if "course" in lowered:
        return f"{row_count} 门课程"
    if "city" in lowered or "cities" in lowered:
        return f"{row_count} 个城市"
    if "title" in lowered:
        return f"{row_count} 个标题"
    return f"{row_count} 条结果"


def summarize(question: str, columns: list[str], rows: list[Sequence[object]]) -> str:
    """Produce a concise, user-facing answer for query results."""
    if not rows:
        return "我没有找到符合条件的结果。"

    row_count = len(rows)
    preview_limit = min(_PREVIEW_LIMIT, row_count)

    display_idx = _pick_display_column(question, columns)
    subject = _extract_subject(question)
    label_source = subject or (columns[display_idx].replace("_", " ") if display_idx is not None else "")
    count_label = _zh_count_phrase(label_source or "result", row_count)

    if display_idx is not None:
        values = [_stringify(row[display_idx]) for row in rows[:preview_limit]]
        preview = _format_preview(values, row_count)
        return f"我找到了 {count_label}：{preview}。"

    first_row = rows[0]
    example = _format_row(columns, first_row)

    if row_count == 1:
        return f"我找到了 1 条结果：{example}。"
    return f"我找到了 {row_count} 条结果。第一条是：{example}。"


__all__ = ["summarize"]
