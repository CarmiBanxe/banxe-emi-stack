"""
tests/test_batch_payments/test_batch_api.py — Tests for Batch Payments API endpoints
IL-BPP-01 | Phase 36 | 12 tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_create_batch_201():
    resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Test Batch",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "DRAFT"
    assert isinstance(data["total_amount"], str)


def test_create_batch_invalid_rail_400():
    resp = client.post(
        "/v1/batch-payments/",
        json={"name": "Bad", "rail": "INVALID", "file_format": "CSV_BANXE", "created_by": "user-1"},
    )
    assert resp.status_code == 400


def test_add_item_201():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Add Item Test",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-2",
        },
    )
    batch_id = batch_resp.json()["id"]
    resp = client.post(
        f"/v1/batch-payments/{batch_id}/items",
        json={
            "ref": "REF001",
            "beneficiary_iban": "GB29NWBK60161331926819",
            "beneficiary_name": "Alice",
            "amount": "100",
            "currency": "GBP",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert isinstance(data["amount"], str)


def test_add_item_invalid_amount_400():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Bad Amount",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-3",
        },
    )
    batch_id = batch_resp.json()["id"]
    resp = client.post(
        f"/v1/batch-payments/{batch_id}/items",
        json={
            "ref": "REF001",
            "beneficiary_iban": "GB29NWBK60161331926819",
            "beneficiary_name": "Alice",
            "amount": "-1",
        },
    )
    assert resp.status_code == 400


def test_validate_batch_200():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Validate Test",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-4",
        },
    )
    batch_id = batch_resp.json()["id"]
    client.post(
        f"/v1/batch-payments/{batch_id}/items",
        json={
            "ref": "REF001",
            "beneficiary_iban": "GB29NWBK60161331926819",
            "beneficiary_name": "Alice",
            "amount": "100",
        },
    )
    resp = client.post(f"/v1/batch-payments/{batch_id}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_valid" in data
    assert "errors" in data


def test_validate_batch_not_found_404():
    resp = client.post("/v1/batch-payments/batch-nonexistent/validate")
    assert resp.status_code == 404


def test_submit_batch_returns_hitl():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Submit Test",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-5",
        },
    )
    batch_id = batch_resp.json()["id"]
    resp = client.post(f"/v1/batch-payments/{batch_id}/submit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hitl_required"] is True
    assert data["autonomy_level"] == "L4"


def test_get_batch_200():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Get Test",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-6",
        },
    )
    batch_id = batch_resp.json()["id"]
    resp = client.get(f"/v1/batch-payments/{batch_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "batch_id" in data


def test_get_batch_not_found_404():
    resp = client.get("/v1/batch-payments/batch-nonexistent")
    assert resp.status_code == 404


def test_list_items_200():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "List Items Test",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-7",
        },
    )
    batch_id = batch_resp.json()["id"]
    resp = client.get(f"/v1/batch-payments/{batch_id}/items")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


def test_dispatch_batch_not_found_returns_404():
    resp = client.post("/v1/batch-payments/batch-nonexistent-dispatch/dispatch")
    assert resp.status_code == 404


def test_get_status_200():
    batch_resp = client.post(
        "/v1/batch-payments/",
        json={
            "name": "Status Test",
            "rail": "FPS",
            "file_format": "CSV_BANXE",
            "created_by": "user-9",
        },
    )
    batch_id = batch_resp.json()["id"]
    resp = client.get(f"/v1/batch-payments/{batch_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data


def test_reconciliation_report_not_found_404():
    resp = client.get("/v1/batch-payments/batch-nonexistent-recon/reconciliation")
    assert resp.status_code == 404
