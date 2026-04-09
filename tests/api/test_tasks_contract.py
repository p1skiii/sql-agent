from __future__ import annotations


def _required_fields(body: dict) -> None:
    for key in (
        "task_id",
        "status",
        "risk_level",
        "thinking_summary",
        "workflow",
        "result",
        "proposal",
        "error",
        "trace",
    ):
        assert key in body


def test_plan_read_task_auto_executes(api_client) -> None:
    response = api_client.post(
        "/api/tasks/plan",
        json={"question": "List all users", "session_id": "s1", "language": "auto"},
    )
    body = response.get_json()

    assert response.status_code == 200
    _required_fields(body)
    assert body["status"] == "SUCCEEDED"
    assert body["risk_level"] == "R0"
    assert body["result"]["row_count"] == 2


def test_plan_write_task_requires_confirmation(api_client) -> None:
    response = api_client.post(
        "/api/tasks/plan",
        json={"question": "Update user 1 name", "session_id": "s2"},
    )
    body = response.get_json()

    assert response.status_code == 200
    _required_fields(body)
    assert body["status"] == "PENDING_CONFIRMATION"
    assert body["risk_level"] == "R1"


def test_confirm_then_show_task(api_client) -> None:
    planned = api_client.post(
        "/api/tasks/plan",
        json={"question": "Update user 1 name", "session_id": "s3"},
    ).get_json()

    confirm_resp = api_client.post(
        f"/api/tasks/{planned['task_id']}/confirm",
        json={"approve": True, "comment": "ok"},
    )
    confirmed = confirm_resp.get_json()

    assert confirm_resp.status_code == 200
    assert confirmed["status"] == "SUCCEEDED"
    assert confirmed["result"]["affected_rows"] == 1

    show_resp = api_client.get(f"/api/tasks/{planned['task_id']}")
    show_body = show_resp.get_json()
    assert show_resp.status_code == 200
    assert show_body["status"] == "SUCCEEDED"


def test_deprecated_run_and_query_endpoints_return_410(api_client) -> None:
    run_resp = api_client.post("/run", json={"question": "List users"})
    query_resp = api_client.post("/api/query", json={"question": "List users"})

    assert run_resp.status_code == 410
    assert query_resp.status_code == 410


def test_task_not_found(api_client) -> None:
    response = api_client.get("/api/tasks/missing-task")
    body = response.get_json()

    assert response.status_code == 404
    assert body["ok"] is False
