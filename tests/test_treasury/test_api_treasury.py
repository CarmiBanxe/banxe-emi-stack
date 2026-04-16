"""
tests/test_treasury/test_api_treasury.py
IL-TLM-01 | Phase 17 — Treasury API endpoint tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import treasury as treasury_router

# Minimal test app — the treasury router is registered separately in api/main.py
_test_app = FastAPI()
_test_app.include_router(treasury_router.router, prefix="/v1")

_NOW = datetime.now(UTC)

client = TestClient(_test_app)


def _mock_agent(
    positions_response=None,
    forecast_response=None,
    sweeps_response=None,
    sweep_propose_response=None,
    approve_response=None,
    recon_response=None,
    reconciliations=None,
):
    agent = MagicMock()
    agent.get_all_positions = AsyncMock(
        return_value=positions_response
        or [
            {
                "pool_id": "pool-001",
                "current_balance": "2500000",
                "required_minimum": "500000",
                "surplus_or_deficit": "2000000",
                "position_count": 0,
                "is_compliant": True,
                "status": "ACTIVE",
                "name": "Primary GBP Pool",
                "currency": "GBP",
            }
        ]
    )
    agent.get_positions = AsyncMock(
        return_value={
            "pool_id": "pool-001",
            "current_balance": "2500000",
            "required_minimum": "500000",
            "surplus_or_deficit": "2000000",
            "position_count": 0,
            "is_compliant": True,
            "status": "ACTIVE",
            "name": "Primary GBP Pool",
            "currency": "GBP",
        }
    )
    agent.run_forecast = AsyncMock(
        return_value=forecast_response
        or {
            "id": "fc-001",
            "pool_id": "pool-001",
            "horizon": "DAYS_7",
            "forecast_amount": "2500000",
            "confidence": "0.50",
            "generated_at": _NOW.isoformat(),
            "model_version": "v1",
            "shortfall_risk": False,
        }
    )
    agent.get_pending_sweeps = AsyncMock(return_value=sweeps_response or [])
    agent.propose_sweep = AsyncMock(
        return_value=sweep_propose_response
        or {
            "id": "sweep-001",
            "pool_id": "pool-001",
            "direction": "SURPLUS_OUT",
            "amount": "50000",
            "currency": "GBP",
            "executed_at": None,
            "proposed_at": _NOW.isoformat(),
            "approved_by": None,
            "description": "",
        }
    )
    agent.approve_sweep = AsyncMock(
        return_value=approve_response
        or {
            "id": "sweep-001",
            "pool_id": "pool-001",
            "direction": "SURPLUS_OUT",
            "amount": "50000",
            "currency": "GBP",
            "executed_at": _NOW.isoformat(),
            "proposed_at": _NOW.isoformat(),
            "approved_by": "mlro",
            "description": "",
        }
    )
    agent.reconcile_account = AsyncMock(
        return_value=recon_response
        or {
            "id": "recon-001",
            "account_id": "acc-001",
            "period_date": _NOW.isoformat(),
            "book_balance": "100000",
            "bank_balance": "100000",
            "variance": "0",
            "status": "MATCHED",
            "reconciled_at": _NOW.isoformat(),
            "notes": "OK",
        }
    )
    agent._reconciler = MagicMock()
    agent._reconciler.list_reconciliations = AsyncMock(return_value=reconciliations or [])
    return agent


# ── GET /v1/treasury/positions ────────────────────────────────────────────────


def test_get_all_positions_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/positions")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── GET /v1/treasury/positions/{pool_id} ──────────────────────────────────────


def test_get_pool_positions_known_pool_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/positions/pool-001")
    assert resp.status_code == 200
    assert resp.json()["pool_id"] == "pool-001"


def test_get_pool_positions_unknown_returns_404() -> None:
    mock_agent = _mock_agent()
    mock_agent.get_positions = AsyncMock(side_effect=ValueError("Pool 'unknown' not found"))
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/positions/unknown")
    assert resp.status_code == 404


# ── GET /v1/treasury/forecasts/{pool_id} ──────────────────────────────────────


def test_run_forecast_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/forecasts/pool-001?horizon=DAYS_7")
    assert resp.status_code == 200
    assert "forecast_amount" in resp.json()


# ── GET /v1/treasury/sweeps/pending ──────────────────────────────────────────


def test_list_pending_sweeps_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/sweeps/pending")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── POST /v1/treasury/sweeps ──────────────────────────────────────────────────


def test_propose_sweep_returns_200_with_id() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/sweeps",
            json={
                "pool_id": "pool-001",
                "direction": "SURPLUS_OUT",
                "amount": "50000",
                "actor": "operator",
            },
        )
    assert resp.status_code == 200
    assert "id" in resp.json()


def test_propose_sweep_invalid_direction_returns_422() -> None:
    mock_agent = _mock_agent()
    mock_agent.propose_sweep = AsyncMock(side_effect=ValueError("Invalid direction"))
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/sweeps",
            json={
                "pool_id": "pool-001",
                "direction": "INVALID",
                "amount": "50000",
                "actor": "operator",
            },
        )
    assert resp.status_code == 422


def test_propose_sweep_direction_surplus_out() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/sweeps",
            json={
                "pool_id": "pool-001",
                "direction": "SURPLUS_OUT",
                "amount": "10000",
                "actor": "op",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["direction"] == "SURPLUS_OUT"


def test_propose_sweep_direction_deficit_in() -> None:
    mock_agent = _mock_agent()
    mock_agent.propose_sweep = AsyncMock(
        return_value={
            "id": "sw-2",
            "pool_id": "pool-001",
            "direction": "DEFICIT_IN",
            "amount": "10000",
            "currency": "GBP",
            "executed_at": None,
            "proposed_at": _NOW.isoformat(),
            "approved_by": None,
            "description": "",
        }
    )
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/sweeps",
            json={
                "pool_id": "pool-001",
                "direction": "DEFICIT_IN",
                "amount": "10000",
                "actor": "op",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["direction"] == "DEFICIT_IN"


# ── POST /v1/treasury/sweeps/{id}/approve ────────────────────────────────────


def test_approve_sweep_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post("/v1/treasury/sweeps/sweep-001/approve", json={"approved_by": "mlro"})
    assert resp.status_code == 200
    assert resp.json()["approved_by"] == "mlro"


# ── GET /v1/treasury/reconciliations ─────────────────────────────────────────


def test_list_reconciliations_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/reconciliations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── POST /v1/treasury/reconcile ──────────────────────────────────────────────


def test_manual_reconcile_returns_200() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/reconcile",
            json={
                "institution": "Barclays",
                "iban": "GB29NWBK60161331926819",
                "balance": "100000",
                "client_money": "95000",
            },
        )
    assert resp.status_code == 200
    assert "status" in resp.json()


# ── Content validation ────────────────────────────────────────────────────────


def test_response_amounts_are_strings() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/positions/pool-001")
    data = resp.json()
    assert isinstance(data["current_balance"], str)
    assert isinstance(data["required_minimum"], str)


def test_forecast_returns_shortfall_risk_boolean() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/forecasts/pool-001?horizon=DAYS_7")
    data = resp.json()
    assert isinstance(data["shortfall_risk"], bool)


def test_positions_response_has_position_count() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/positions/pool-001")
    assert "position_count" in resp.json()


def test_forecast_returns_confidence_as_string() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/forecasts/pool-001?horizon=DAYS_14")
    assert isinstance(resp.json()["confidence"], str)


def test_all_positions_is_non_empty_list() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.get("/v1/treasury/positions")
    assert len(resp.json()) > 0


def test_propose_sweep_missing_required_field_returns_422() -> None:
    # Missing 'actor' field → Pydantic validation error
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/sweeps",
            json={
                "pool_id": "pool-001",
                "direction": "SURPLUS_OUT",
                "amount": "50000",
                # actor missing
            },
        )
    assert resp.status_code == 422


def test_reconcile_response_has_variance() -> None:
    mock_agent = _mock_agent()
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post(
            "/v1/treasury/reconcile",
            json={
                "institution": "Barclays",
                "iban": "GB29NWBK60161331926819",
                "balance": "100000",
                "client_money": "95000",
            },
        )
    assert "variance" in resp.json()


def test_approve_sweep_not_found_returns_404() -> None:
    mock_agent = _mock_agent()
    mock_agent.approve_sweep = AsyncMock(side_effect=KeyError("Sweep not found"))
    with patch("api.routers.treasury._get_agent", return_value=mock_agent):
        resp = client.post("/v1/treasury/sweeps/bad-id/approve", json={"approved_by": "mlro"})
    assert resp.status_code == 404
