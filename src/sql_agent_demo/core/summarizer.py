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


def summarize(question: str, columns: list[str], rows: list[Sequence[object]]) -> str:
    """Produce a concise, user-facing summary for query results."""
    if not rows:
        return f"No results found for '{question}'."

    row_count = len(rows)
    preview_limit = min(_PREVIEW_LIMIT, row_count)

    display_idx = _pick_display_column(question, columns)
    subject = _extract_subject(question)
    label_source = subject or (columns[display_idx].replace("_", " ") if display_idx is not None else "")
    count_label = _label_for_count(label_source or "result", row_count)
    prefix = f"{row_count} {count_label}"

    if display_idx is not None and len(columns) > 1:
        # If multiple columns are requested, show compact row previews
        preview_rows = []
        for row in rows[:preview_limit]:
            parts = [f"{col}: {_stringify(row[idx])}" for idx, col in enumerate(columns)]
            preview_rows.append(" | ".join(parts))
        preview = "; ".join(preview_rows)
        extra = row_count - preview_limit
        if extra > 0:
            preview = f"{preview} (+{extra} more)"
        return f"{prefix}: {preview}"

    if display_idx is not None:
        values = [_stringify(row[display_idx]) for row in rows[:preview_limit]]
        preview = ", ".join(values)
        extra = row_count - preview_limit
        if extra > 0:
            preview = f"{preview} (+{extra} more)"
        return f"{prefix}: {preview}"

    first_row = rows[0]
    pairs = [f"{col}: {_stringify(val)}" for col, val in zip(columns, first_row)]
    example = ", ".join(pairs)

    if row_count == 1:
        return f"{prefix}: {example}"
    return f"{prefix}. Example -> {example}"


__all__ = ["summarize"]
