"""
tests/test_crypto_custody/test_crypto_api.py — Tests for Crypto Custody API endpoints
IL-CDC-01 | Phase 35 | 15 tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_create_wallet_200():
    resp = client.post(
        "/v1/crypto/wallets",
        json={
            "owner_id": "test-owner",
            "asset_type": "ETH",
            "wallet_type": "HOT",
            "network": "MAINNET",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["asset_type"] == "ETH"
    assert "balance" in data


def test_create_wallet_invalid_asset_type_400():
    resp = client.post(
        "/v1/crypto/wallets",
        json={"owner_id": "owner-x", "asset_type": "INVALID", "wallet_type": "HOT"},
    )
    assert resp.status_code == 400


def test_list_wallets_200():
    resp = client.get("/v1/crypto/wallets?owner_id=owner-001")
    assert resp.status_code == 200
    data = resp.json()
    assert "wallets" in data
    assert len(data["wallets"]) == 3


def test_get_wallet_200():
    resp = client.get("/v1/crypto/wallets/wallet-btc-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "wallet-btc-001"


def test_get_wallet_404():
    resp = client.get("/v1/crypto/wallets/wallet-nonexistent")
    assert resp.status_code == 404


def test_get_balance_200():
    resp = client.get("/v1/crypto/wallets/wallet-btc-001/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert "balance" in data
    assert isinstance(data["balance"], str)


def test_get_balance_404():
    resp = client.get("/v1/crypto/wallets/wallet-nonexistent/balance")
    assert resp.status_code == 404


def test_archive_wallet_returns_hitl():
    resp = client.post("/v1/crypto/wallets/wallet-btc-001/archive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hitl_required"] is True
    assert data["autonomy_level"] == "L4"


def test_archive_wallet_not_found_404():
    resp = client.post("/v1/crypto/wallets/wallet-nonexistent/archive")
    assert resp.status_code == 404


def test_initiate_transfer_201():
    resp = client.post(
        "/v1/crypto/transfers",
        json={
            "from_wallet_id": "wallet-eth-001",
            "to_address": "0x" + "a" * 40,
            "amount": "0.1",
            "asset_type": "ETH",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "PENDING"
    assert isinstance(data["amount"], str)


def test_initiate_transfer_invalid_400():
    resp = client.post(
        "/v1/crypto/transfers",
        json={"from_wallet_id": "wallet-btc-001", "to_address": "addr", "amount": "-1"},
    )
    assert resp.status_code == 400


def test_get_transfer_404():
    resp = client.get("/v1/crypto/transfers/txfr-nonexistent")
    assert resp.status_code == 404


def test_confirm_transfer_400_without_txhash():
    resp = client.post(
        "/v1/crypto/transfers/txfr-nonexistent/confirm",
        json={},
    )
    assert resp.status_code in (400, 404)


def test_travel_rule_check_200():
    resp = client.post(
        "/v1/crypto/travel-rule/check",
        json={"amount_eur": "1500", "jurisdiction": "GB"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["travel_rule_required"] is True
    assert data["jurisdiction_screening"] == "PASS"


def test_travel_rule_check_blocked_jurisdiction():
    resp = client.post(
        "/v1/crypto/travel-rule/check",
        json={"amount_eur": "100", "jurisdiction": "RU"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jurisdiction_screening"] == "BLOCKED"
