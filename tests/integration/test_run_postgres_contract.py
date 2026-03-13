# Tests the Flask /run contract on the PostgreSQL path with fake models.
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.fake_model]


def test_run_postgres_read_success_returns_result_objects(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        sql="SELECT id, name FROM students ORDER BY id LIMIT 2",
        base_overrides={
            "db_backend": "postgres",
            "db_url": postgres_url,
            "schema_path": str(data_dir / "schema.sql"),
            "seed_path": str(data_dir / "seed.sql"),
            "overwrite_db": True,
        },
    )

    response = client.post("/run", json={"question": "List the ids and names of all students."})
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mode"] == "READ"
    assert body["result"]["rows"] == [
        {"id": 1, "name": "Alice Johnson"},
        {"id": 2, "name": "Brian Smith"},
    ]
    assert body["result"]["row_count"] == 2


def test_run_postgres_write_dry_run_returns_affected_rows(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
        base_overrides={
            "db_backend": "postgres",
            "db_url": postgres_url,
            "schema_path": str(data_dir / "schema.sql"),
            "seed_path": str(data_dir / "seed.sql"),
            "overwrite_db": True,
            "allow_write": True,
        },
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
    assert body["result"]["columns"] == ["id", "name", "city", "major", "gpa"]
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["name"] == "Alice Johnson"
    assert body["result"]["rows"][0]["gpa"] == pytest.approx(3.9)
