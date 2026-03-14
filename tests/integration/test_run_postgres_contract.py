# Tests the Flask /run contract on the PostgreSQL path with fake models.
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.fake_model]


class RaisingSqlModel:
    def generate_json(self, messages):
        _ = messages
        raise ConnectionRefusedError("[Errno 61] Connection refused")


def test_run_postgres_read_success_returns_result_objects(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        sql=(
            "SELECT p.sku, p.name, i.quantity "
            "FROM products p JOIN inventory i ON i.product_id = p.id "
            "JOIN categories c ON c.id = p.category_id "
            "WHERE c.name = 'Laptops' ORDER BY p.id LIMIT 2"
        ),
        base_overrides={
            "db_backend": "postgres",
            "db_url": postgres_url,
            "schema_path": str(data_dir / "schema.sql"),
            "seed_path": str(data_dir / "seed.sql"),
            "overwrite_db": True,
        },
    )

    response = client.post("/run", json={"question": "Show the inventory for all laptop products."})
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mode"] == "READ"
    assert body["result"]["rows"] == [
        {"sku": "LAP-001", "name": "Aurora Pro 14", "quantity": 12},
        {"sku": "LAP-002", "name": "Nimbus Air 13", "quantity": 7},
    ]
    assert body["result"]["row_count"] == 2


def test_run_postgres_write_dry_run_returns_affected_rows(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE inventory SET quantity = 15 WHERE product_id = 1",
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
            "question": "Update the inventory quantity for product LAP-001 to 15.",
            "allow_write": True,
            "dry_run": True,
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mode"] == "WRITE"
    assert body["dry_run"] is True
    assert body["result"]["columns"] == ["product_id", "quantity", "reserved_quantity", "updated_at"]
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["product_id"] == 1
    assert body["result"]["rows"][0]["quantity"] == 15


def test_run_postgres_write_commit_returns_committed_order_state(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE orders SET status = 'paid' WHERE order_number = 'ORD-1002'",
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
            "question": "Change order ORD-1002 to paid.",
            "allow_write": True,
            "dry_run": False,
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mode"] == "WRITE"
    assert body["dry_run"] is False
    assert body["result"]["columns"] == ["id", "user_id", "order_number", "status", "total_amount", "created_at"]
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["order_number"] == "ORD-1002"
    assert body["result"]["rows"][0]["status"] == "paid"


def test_run_postgres_write_without_where_is_rejected(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql="UPDATE inventory SET quantity = 0",
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
            "question": "Set every inventory quantity to zero.",
            "allow_write": True,
            "dry_run": True,
        },
    )
    body = response.get_json()

    assert response.status_code == 400
    assert body["ok"] is False
    assert body["status"] == "UNSUPPORTED"
    assert "WHERE clause" in body["reason"]


def test_run_postgres_read_falls_back_when_llm_endpoint_is_unreachable(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        sql_model=RaisingSqlModel(),
        base_overrides={
            "db_backend": "postgres",
            "db_url": postgres_url,
            "schema_path": str(data_dir / "schema.sql"),
            "seed_path": str(data_dir / "seed.sql"),
            "overwrite_db": True,
        },
    )

    response = client.post("/run", json={"question": "Show the inventory for all laptop products."})
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["result"]["row_count"] == 2
    assert body["result"]["rows"][0]["sku"] == "LAP-001"
    assert body["result"]["rows"][0]["quantity"] == 12


def test_run_postgres_write_falls_back_when_llm_endpoint_is_unreachable(
    api_client_factory,
    data_dir: Path,
    postgres_url: str,
) -> None:
    client = api_client_factory(
        intent_label="WRITE",
        sql_model=RaisingSqlModel(),
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
            "question": "Update the inventory quantity for product LAP-001 to 15.",
            "allow_write": True,
            "dry_run": True,
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0]["product_id"] == 1
    assert body["result"]["rows"][0]["quantity"] == 15
