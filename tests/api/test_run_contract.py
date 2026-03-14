# Tests the Flask /run contract using deterministic fake models.
from __future__ import annotations

import pytest

from sql_agent_demo.interfaces import api as api_module

pytestmark = [pytest.mark.api, pytest.mark.fake_model]


def test_run_read_success_returns_structured_result(api_client_factory) -> None:
    client = api_client_factory(sql="SELECT id, name FROM students ORDER BY id")

    response = client.post("/run", json={"question": "List the ids and names of all students."})
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["status"] == "SUCCESS"
    assert body["mode"] == "READ"
    assert body["result"]["columns"] == ["id", "name"]
    assert body["result"]["rows"][:2] == [
        {"id": 1, "name": "Alice Johnson"},
        {"id": 2, "name": "Brian Smith"},
    ]
    assert body["result"]["row_count"] == len(body["result"]["rows"])
    assert isinstance(body["trace"], list)


def test_run_write_dry_run_success_distinguishes_execution_flags(api_client_factory) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
    )

    response = client.post(
        "/run",
        json={
            "question": "Update the student named Alice Johnson to have GPA 3.9.",
            "allow_write": True,
            "dry_run": True,
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mode"] == "WRITE"
    assert body["dry_run"] is True
    assert body["summary"] == "演练模式：将更新 1 条记录"
    assert body["result"]["columns"] == ["id", "name", "city", "major", "gpa"]
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["name"] == "Alice Johnson"
    assert body["result"]["rows"][0]["gpa"] == pytest.approx(3.9)


def test_run_write_commit_success_returns_committed_payload(api_client_factory) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
    )

    response = client.post(
        "/run",
        json={
            "question": "Update the student named Alice Johnson to have GPA 3.9.",
            "allow_write": True,
            "dry_run": False,
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mode"] == "WRITE"
    assert body["dry_run"] is False
    assert body["summary"] == "已更新 1 条记录"
    assert body["result"]["columns"] == ["id", "name", "city", "major", "gpa"]
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["name"] == "Alice Johnson"
    assert body["result"]["rows"][0]["gpa"] == pytest.approx(3.9)


def test_run_unsupported_returns_400_and_contract_body(api_client_factory) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
        base_overrides={"allow_write": False},
    )

    response = client.post("/run", json={"question": "Update the student named Alice Johnson to have GPA 3.9."})
    body = response.get_json()

    assert response.status_code == 400
    assert body["ok"] is False
    assert body["status"] == "UNSUPPORTED"
    assert body["reason"] == "Write operations are disabled. Use --allow-write to enable."
    assert body["result"] is None
    assert body["diagnosis"]["category"] == "GUARD"


def test_run_bad_request_requires_question(api_client_factory) -> None:
    client = api_client_factory()

    response = client.post("/run", json={})
    body = response.get_json()

    assert response.status_code == 400
    assert body == {"ok": False, "error": "question is required"}


def test_run_execution_error_returns_500(api_client_factory) -> None:
    client = api_client_factory(sql="SELECT missing_col FROM students")

    response = client.post("/run", json={"question": "Show the missing_col values."})
    body = response.get_json()

    assert response.status_code == 500
    assert body["ok"] is False
    assert body["status"] == "ERROR"
    assert body["diagnosis"]["category"] == "EXECUTION_ERROR"
    assert body["reason"] in {"no such column: missing_col", "Failed to execute repaired SQL."}


def test_api_query_matches_run_contract(api_client_factory) -> None:
    client = api_client_factory(sql="SELECT id, name FROM students ORDER BY id LIMIT 6")

    response = client.post("/api/query", json={"question": "List the ids and names of all students."})
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["status"] == "SUCCESS"
    assert body["mode"] == "READ"
    assert body["result"]["columns"] == ["id", "name"]
    assert body["result"]["rows"][0]["name"] == "Alice Johnson"


def test_api_query_requires_question(api_client_factory) -> None:
    client = api_client_factory()

    response = client.post("/api/query", json={})
    body = response.get_json()

    assert response.status_code == 400
    assert body == {"ok": False, "error": "question is required"}


def test_api_schema_returns_table_field_type_and_row_count(api_client_factory) -> None:
    client = api_client_factory()

    response = client.get("/api/schema")
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["backend"] == "sqlite"
    assert body["database"]["backend"] == "sqlite"
    assert [table["name"] for table in body["tables"]] == ["courses", "enrollments", "students"]
    students_table = body["tables"][2]
    assert students_table["row_count"] == 6
    assert students_table["columns"] == [
        {"name": "id", "type": "INTEGER"},
        {"name": "name", "type": "TEXT"},
        {"name": "city", "type": "TEXT"},
        {"name": "major", "type": "TEXT"},
        {"name": "gpa", "type": "REAL"},
    ]


def test_api_examples_returns_stable_example_questions(api_client_factory) -> None:
    client = api_client_factory()

    response = client.get("/api/examples")
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert len(body["examples"]) >= 4
    assert body["examples"][0] == {
        "id": "students-list",
        "question": "List the ids and names of all students.",
    }


def test_api_health_reports_database_ready(api_client_factory) -> None:
    client = api_client_factory()

    response = client.get("/api/health")
    body = response.get_json()

    assert response.status_code == 200
    assert body == {
        "ok": True,
        "status": "healthy",
        "service": "sql-agent-demo",
        "database": {
            "backend": "sqlite",
            "ready": True,
        },
        "config": {
            "allow_write": True,
            "dry_run_default": True,
            "guard_level": "strict",
        },
    }


def test_api_health_returns_500_when_database_probe_fails(monkeypatch: pytest.MonkeyPatch, tmp_path, data_dir) -> None:
    monkeypatch.setattr(api_module, "load_env_file", lambda: None)
    monkeypatch.setattr(api_module, "setup_logging", lambda: None)

    class BrokenHandle:
        def execute_select(self, sql: str):
            raise RuntimeError("database probe failed")

        def get_schema_overview(self):
            raise RuntimeError("schema unavailable")

    monkeypatch.setattr(api_module, "init_sandbox_db", lambda config: BrokenHandle())
    monkeypatch.setattr(
        api_module,
        "build_models",
        lambda config: (object(), object()),
    )

    app = api_module.create_app(
        {
            "db_backend": "sqlite",
            "db_path": str(tmp_path / "broken.db"),
            "schema_path": str(data_dir / "schema.sql"),
            "seed_path": str(data_dir / "seed.sql"),
            "overwrite_db": False,
        }
    )
    app.testing = True
    client = app.test_client()

    response = client.get("/api/health")
    body = response.get_json()

    assert response.status_code == 500
    assert body["ok"] is False
    assert body["status"] == "unhealthy"
    assert body["database"] == {
        "backend": "sqlite",
        "ready": False,
    }
    assert body["error"] == "database probe failed"
