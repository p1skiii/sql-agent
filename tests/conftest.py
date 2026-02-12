# Fixtures for model selection, sandbox database setup, and read-pipeline agent context.
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sql_agent_demo.core.models import AgentConfig, AgentContext, IntentType, LlmNotConfigured
from sql_agent_demo.infra.db import init_sandbox_db
from sql_agent_demo.infra.env import load_env_file
from sql_agent_demo.infra.llm_provider import build_llm_from_name


class AlwaysReadIntentModel:
    """Predicts a read intent for every question."""

    def predict(self, question: str) -> IntentType:
        _ = question
        return IntentType.READ_SIMPLE

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        _ = messages
        return {"label": "READ_SIMPLE"}


class FakeSqlModel:
    """Emits a deterministic read-only SQL statement for testing."""

    def __init__(self, sql: str | None = None) -> None:
        self.sql = sql or "SELECT id, name, city, major, gpa FROM students"

    def generate(self, messages: list[dict[str, Any]]) -> str:
        _ = messages
        return self.sql

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        _ = messages
        return {"sql": self.sql}


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


load_env_file()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--model",
        action="store",
        default="fake",
        help="Model name for integration tests, e.g. fake, deepseek-v3, gemini-2.5-flash",
    )


@pytest.fixture
def model_name(request: pytest.FixtureRequest) -> str:
    return str(request.config.getoption("--model"))


@pytest.fixture
def db_config(tmp_path: Path, data_dir: Path) -> AgentConfig:
    db_path = tmp_path / "sandbox.db"
    return AgentConfig(
        top_k=5,
        max_rows=10,
        allow_trace=True,
        db_path=str(db_path),
        schema_path=str(data_dir / "schema.sql"),
        seed_path=str(data_dir / "seed.sql"),
        overwrite_db=True,
        intent_model_name="fake-intent",
        sql_model_name="fake-sql",
        selfcheck_enabled=False,
        language="en",
    )


@pytest.fixture
def db_handle(db_config: AgentConfig):
    return init_sandbox_db(db_config)


@pytest.fixture
def read_agent_ctx(model_name: str, db_config: AgentConfig, db_handle):
    if model_name == "fake":
        intent_model = AlwaysReadIntentModel()
        sql_model = FakeSqlModel()
    else:
        intent_model = AlwaysReadIntentModel()
        try:
            sql_model = build_llm_from_name(model_name)
        except LlmNotConfigured:
            pytest.skip("NO_API_KEY")

    # Ensure downstream consumers always have these toggles available.
    db_config.max_rows = db_config.max_rows or 10
    db_config.allow_trace = True

    return AgentContext(
        config=db_config,
        db_handle=db_handle,
        intent_model=intent_model,
        sql_model=sql_model,
    )
