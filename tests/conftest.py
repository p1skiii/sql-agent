# Fixtures for model selection, sandbox database setup, and read-pipeline agent context.
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

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


class FixedIntentModel:
    """Returns a fixed label payload for intent detection tests."""

    def __init__(self, label: str) -> None:
        self.label = label

    def generate_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        _ = messages
        return {"label": self.label}


class FixedSqlModel:
    """Returns a fixed SQL payload for read or write generation tests."""

    def __init__(self, sql: str) -> None:
        self.sql = sql

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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


@pytest.fixture(scope="session")
def postgres_url() -> str:
    if shutil.which("docker") is None:
        pytest.skip("docker is required for PostgreSQL integration tests")

    repo_root = Path(__file__).resolve().parents[1]
    compose_file = repo_root / "docker-compose.postgres.yml"
    port = _free_port()
    project = f"sql-agent-test-{uuid.uuid4().hex[:8]}"
    env = {
        **os.environ,
        "SQL_AGENT_POSTGRES_PORT": str(port),
    }

    subprocess.run(
        ["docker", "compose", "-p", project, "-f", str(compose_file), "up", "-d", "postgres"],
        check=True,
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            probe = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    project,
                    "-f",
                    str(compose_file),
                    "exec",
                    "-T",
                    "postgres",
                    "pg_isready",
                    "-U",
                    "sql_agent",
                    "-d",
                    "sql_agent_demo",
                ],
                cwd=repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Timed out waiting for PostgreSQL container")

        yield f"postgresql+psycopg://sql_agent:sql_agent@127.0.0.1:{port}/sql_agent_demo"
    finally:
        subprocess.run(
            ["docker", "compose", "-p", project, "-f", str(compose_file), "down", "-v"],
            cwd=repo_root,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


@pytest.fixture
def api_client_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data_dir: Path) -> Callable[..., Any]:
    from sql_agent_demo.interfaces import api as api_module

    monkeypatch.setattr(api_module, "load_env_file", lambda: None)
    monkeypatch.setattr(api_module, "setup_logging", lambda: None)

    counter = 0

    def _build_client(
        *,
        intent_label: str = "READ_SIMPLE",
        sql: str = "SELECT id, name FROM students ORDER BY id LIMIT 6",
        base_overrides: dict[str, Any] | None = None,
        intent_model: Any | None = None,
        sql_model: Any | None = None,
    ):
        nonlocal counter
        counter += 1
        db_path = tmp_path / f"api-{counter}.db"
        overrides = {
            "db_backend": "sqlite",
            "db_path": str(db_path),
            "schema_path": str(data_dir / "schema.sql"),
            "seed_path": str(data_dir / "seed.sql"),
            "overwrite_db": True,
            "allow_trace": True,
            "allow_write": True,
            "dry_run_default": True,
            "allow_llm_summary": False,
            "intent_model_name": "fake-intent",
            "sql_model_name": "fake-sql",
        }
        if base_overrides:
            overrides.update(base_overrides)

        fixed_intent_model = intent_model or FixedIntentModel(intent_label)
        fixed_sql_model = sql_model or FixedSqlModel(sql)
        monkeypatch.setattr(api_module, "build_models", lambda config: (fixed_intent_model, fixed_sql_model))

        app = api_module.create_app(overrides)
        app.testing = True
        return app.test_client()

    return _build_client
