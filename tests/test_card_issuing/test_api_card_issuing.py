"""
tests/test_card_issuing/test_api_card_issuing.py
IL-CIM-01 | Phase 19 -- CardIssuing REST API tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import card_issuing as card_issuing_router

_test_app = FastAPI()
_test_app.include_router(card_issuing_router.router, prefix="/v1")


def _make_mock_agent():
    agent = MagicMock()
    agent.issue_card = AsyncMock(
        return_value={
            "id": "card-test-001",
            "entity_id": "ent-001",
            "card_type": "VIRTUAL",
            "network": "MASTERCARD",
            "bin_range_id": "bin-mc-001",
            "last_four": "1234",
            "expiry_month": 4,
            "expiry_year": 2029,
            "status": "PENDING",
            "created_at": "2026-04-16T00:00:00+00:00",
            "activated_at": None,
            "name_on_card": "Test User",
        }
    )
    agent.activate_card = AsyncMock(
        return_value={
            "id": "card-test-001",
            "entity_id": "ent-001",
            "card_type": "VIRTUAL",
            "network": "MASTERCARD",
            "bin_range_id": "bin-mc-001",
            "last_four": "1234",
            "expiry_month": 4,
            "expiry_year": 2029,
            "status": "ACTIVE",
            "created_at": "2026-04-16T00:00:00+00:00",
            "activated_at": "2026-04-16T01:00:00+00:00",
            "name_on_card": "Test User",
        }
    )
    agent.set_pin = AsyncMock(return_value={"success": True, "card_id": "card-test-001"})
    agent.freeze_card = AsyncMock(
        return_value={
            "id": "card-test-001",
            "status": "FROZEN",
            "entity_id": "ent-001",
            "card_type": "VIRTUAL",
            "network": "MASTERCARD",
            "bin_range_id": "bin-mc-001",
            "last_four": "1234",
            "expiry_month": 4,
            "expiry_year": 2029,
            "created_at": "2026-04-16T00:00:00+00:00",
            "activated_at": None,
            "name_on_card": "Test User",
        }
    )
    agent.unfreeze_card = AsyncMock(
        return_value={
            "id": "card-test-001",
            "status": "ACTIVE",
            "entity_id": "ent-001",
            "card_type": "VIRTUAL",
            "network": "MASTERCARD",
            "bin_range_id": "bin-mc-001",
            "last_four": "1234",
            "expiry_month": 4,
            "expiry_year": 2029,
            "created_at": "2026-04-16T00:00:00+00:00",
            "activated_at": None,
            "name_on_card": "Test User",
        }
    )
    agent.block_card = AsyncMock(
        return_value={
            "id": "card-test-001",
            "status": "BLOCKED",
            "entity_id": "ent-001",
            "card_type": "VIRTUAL",
            "network": "MASTERCARD",
            "bin_range_id": "bin-mc-001",
            "last_four": "1234",
            "expiry_month": 4,
            "expiry_year": 2029,
            "created_at": "2026-04-16T00:00:00+00:00",
            "activated_at": None,
            "name_on_card": "Test User",
        }
    )
    agent.set_limits = AsyncMock(
        return_value={
            "card_id": "card-test-001",
            "period": "PER_TRANSACTION",
            "limit_amount": "500.00",
            "currency": "GBP",
            "blocked_mccs": [],
            "geo_restrictions": [],
        }
    )
    agent.authorise_transaction = AsyncMock(
        return_value={
            "id": "auth-test-001",
            "card_id": "card-test-001",
            "amount": "50.00",
            "currency": "GBP",
            "merchant_name": "Tesco",
            "result": "APPROVED",
            "decline_reason": None,
            "authorised_at": "2026-04-16T00:00:00+00:00",
        }
    )
    agent.get_card = AsyncMock(
        return_value={
            "id": "card-test-001",
            "entity_id": "ent-001",
            "status": "ACTIVE",
            "card_type": "VIRTUAL",
            "network": "MASTERCARD",
            "bin_range_id": "bin-mc-001",
            "last_four": "1234",
            "expiry_month": 4,
            "expiry_year": 2029,
            "created_at": "2026-04-16T00:00:00+00:00",
            "activated_at": None,
            "name_on_card": "Test User",
        }
    )
    agent.list_transactions = AsyncMock(return_value=[])
    return agent


def test_post_issue_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/issue",
            json={
                "entity_id": "ent-001",
                "card_type": "VIRTUAL",
                "network": "MASTERCARD",
                "name_on_card": "Test User",
                "actor": "admin",
            },
        )
    assert resp.status_code == 200


def test_post_activate_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post("/v1/cards/card-test-001/activate", json={"actor": "admin"})
    assert resp.status_code == 200


def test_post_pin_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post("/v1/cards/card-test-001/pin", json={"pin": "1234", "actor": "admin"})
    assert resp.status_code == 200


def test_post_freeze_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/card-test-001/freeze", json={"actor": "admin", "reason": "check"}
        )
    assert resp.status_code == 200


def test_post_unfreeze_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post("/v1/cards/card-test-001/unfreeze", json={"actor": "admin"})
    assert resp.status_code == 200


def test_post_block_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/card-test-001/block", json={"actor": "admin", "reason": "fraud"}
        )
    assert resp.status_code == 200


def test_post_limits_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/card-test-001/limits",
            json={
                "period": "PER_TRANSACTION",
                "amount": "500.00",
                "currency": "GBP",
                "blocked_mccs": [],
                "actor": "admin",
            },
        )
    assert resp.status_code == 200


def test_post_authorise_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/card-test-001/authorise",
            json={
                "amount": "50.00",
                "currency": "GBP",
                "merchant_name": "Tesco",
                "mcc": "5411",
                "country": "GB",
                "actor": "pos",
            },
        )
    assert resp.status_code == 200


def test_get_card_returns_200() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.get("/v1/cards/card-test-001")
    assert resp.status_code == 200


def test_get_transactions_returns_200_list() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.get("/v1/cards/card-test-001/transactions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_unknown_card_returns_404() -> None:
    agent = _make_mock_agent()
    agent.get_card = AsyncMock(return_value=None)
    with patch("api.routers.card_issuing._get_agent", return_value=agent):
        client = TestClient(_test_app)
        resp = client.get("/v1/cards/unknown-id")
    assert resp.status_code == 404


def test_post_invalid_card_type_returns_422() -> None:
    agent = _make_mock_agent()
    agent.issue_card = AsyncMock(side_effect=ValueError("Invalid card type"))
    with patch("api.routers.card_issuing._get_agent", return_value=agent):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/issue",
            json={
                "entity_id": "ent-001",
                "card_type": "INVALID",
                "network": "MASTERCARD",
                "name_on_card": "Test User",
                "actor": "admin",
            },
        )
    assert resp.status_code == 422


def test_authorise_amount_is_string_in_request() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/card-test-001/authorise",
            json={
                "amount": "99.99",
                "currency": "GBP",
                "merchant_name": "Shop",
                "mcc": "5411",
                "country": "GB",
                "actor": "pos",
            },
        )
    assert resp.status_code == 200


def test_issue_and_activate_flow() -> None:
    with patch("api.routers.card_issuing._get_agent", return_value=_make_mock_agent()):
        client = TestClient(_test_app)
        issue_resp = client.post(
            "/v1/cards/issue",
            json={
                "entity_id": "ent-001",
                "card_type": "VIRTUAL",
                "network": "MASTERCARD",
                "name_on_card": "A User",
                "actor": "admin",
            },
        )
        assert issue_resp.status_code == 200
        card_id = issue_resp.json()["id"]

        activate_resp = client.post(f"/v1/cards/{card_id}/activate", json={"actor": "admin"})
        assert activate_resp.status_code == 200


def test_issue_visa_card() -> None:
    agent = _make_mock_agent()
    visa_card = {
        "id": "card-visa-001",
        "entity_id": "ent-001",
        "status": "PENDING",
        "card_type": "VIRTUAL",
        "network": "VISA",
        "bin_range_id": "bin-visa-001",
        "last_four": "5678",
        "expiry_month": 4,
        "expiry_year": 2029,
        "created_at": "2026-04-16T00:00:00+00:00",
        "activated_at": None,
        "name_on_card": "Test User",
    }
    agent.issue_card = AsyncMock(return_value=visa_card)
    with patch("api.routers.card_issuing._get_agent", return_value=agent):
        client = TestClient(_test_app)
        resp = client.post(
            "/v1/cards/issue",
            json={
                "entity_id": "ent-001",
                "card_type": "VIRTUAL",
                "network": "VISA",
                "name_on_card": "Test User",
                "actor": "admin",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["network"] == "VISA"
