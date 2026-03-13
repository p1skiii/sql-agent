# Tests the Flask /run contract using deterministic fake models.
from __future__ import annotations

import pytest

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
