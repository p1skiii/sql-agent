"""Lightweight language detection and localized message templates."""
from __future__ import annotations

import re


_LANG_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"[\u3040-\u30ff]", "ja"),  # Hiragana + Katakana
    (r"[\uac00-\ud7af]", "ko"),  # Hangul
    (r"[\u3400-\u9fff\uf900-\ufaff]", "zh"),  # Han
)

_MESSAGES: dict[str, dict[str, str]] = {
    "MODEL_UNAVAILABLE": {
        "en": "Model is unavailable. Please check model configuration and retry.",
        "zh": "模型当前不可用，请检查配置后重试。",
        "ja": "モデルを利用できません。設定を確認して再試行してください。",
        "ko": "모델을 사용할 수 없습니다. 설정을 확인한 뒤 다시 시도하세요.",
    },
    "UNSUPPORTED_INTENT": {
        "en": "This request is not supported by the current task policy.",
        "zh": "当前任务策略不支持该请求。",
        "ja": "現在のタスクポリシーではこの要求はサポートされていません。",
        "ko": "현재 작업 정책에서 이 요청은 지원되지 않습니다.",
    },
    "SQL_GENERATION_FAILED": {
        "en": "Failed to generate SQL for this task.",
        "zh": "未能为该任务生成 SQL。",
        "ja": "このタスクの SQL 生成に失敗しました。",
        "ko": "이 작업에 대한 SQL 생성에 실패했습니다.",
    },
    "SQL_GUARD_BLOCKED": {
        "en": "SQL was blocked by guard policy.",
        "zh": "SQL 被安全策略拦截。",
        "ja": "SQL はガードポリシーによりブロックされました。",
        "ko": "SQL이 가드 정책에 의해 차단되었습니다.",
    },
    "EXECUTION_FAILED": {
        "en": "Task execution failed.",
        "zh": "任务执行失败。",
        "ja": "タスク実行に失敗しました。",
        "ko": "작업 실행에 실패했습니다.",
    },
    "DDL_BLOCKED": {
        "en": "DDL is blocked by default and requires a proposal workflow.",
        "zh": "DDL 默认被阻断，需走提案流程。",
        "ja": "DDL は既定でブロックされ、提案フローが必要です。",
        "ko": "DDL은 기본적으로 차단되며 제안 워크플로가 필요합니다.",
    },
    "USER_REJECTED": {
        "en": "Execution was rejected by user confirmation.",
        "zh": "用户确认拒绝执行。",
        "ja": "ユーザー確認により実行が拒否されました。",
        "ko": "사용자 확인으로 실행이 거부되었습니다.",
    },
    "TASK_NOT_FOUND": {
        "en": "Task was not found.",
        "zh": "未找到任务。",
        "ja": "タスクが見つかりません。",
        "ko": "작업을 찾을 수 없습니다.",
    },
    "INVALID_CONFIRMATION": {
        "en": "Task is not in a confirmable state.",
        "zh": "任务当前不可确认执行。",
        "ja": "タスクは確認可能な状態ではありません。",
        "ko": "작업이 확인 가능한 상태가 아닙니다.",
    },
}


def detect_language(text: str) -> str:
    for pattern, lang in _LANG_PATTERNS:
        if re.search(pattern, text):
            return lang
    return "en"


def localize(code: str, language: str, fallback: str | None = None) -> str:
    table = _MESSAGES.get(code, {})
    if language in table:
        return table[language]
    if "en" in table:
        return table["en"]
    return fallback or code


def summarize_read(language: str, row_count: int) -> str:
    if language == "zh":
        return f"查询成功，返回 {row_count} 条记录。"
    if language == "ja":
        return f"クエリ成功。{row_count} 件の行を返しました。"
    if language == "ko":
        return f"조회 성공, {row_count}개 행을 반환했습니다."
    return f"Read query succeeded with {row_count} rows."


def summarize_write(language: str, affected: int) -> str:
    if language == "zh":
        return f"写入成功，影响 {affected} 条记录。"
    if language == "ja":
        return f"更新成功。{affected} 件に影響しました。"
    if language == "ko":
        return f"쓰기 작업 성공, {affected}개 행에 영향이 있었습니다."
    return f"Write operation succeeded; affected {affected} rows."


__all__ = ["detect_language", "localize", "summarize_read", "summarize_write"]
