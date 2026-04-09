from __future__ import annotations

from sql_agent_demo.core.i18n import detect_language, localize


def test_detect_language_handles_zh_ja_ko_and_en() -> None:
    assert detect_language("今天查询库存") == "zh"
    assert detect_language("在庫を見せて") == "ja"
    assert detect_language("재고 보여줘") == "ko"
    assert detect_language("show all users") == "en"


def test_localize_returns_language_specific_message() -> None:
    assert "模型" in localize("MODEL_UNAVAILABLE", "zh")
    assert "model" in localize("MODEL_UNAVAILABLE", "en").lower()
