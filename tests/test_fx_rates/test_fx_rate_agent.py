"""Tests for FXRateAgent — schedule_daily_fetch, override → HITLProposal.

IL-FXR-01 | Phase 52A | Sprint 37
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.fx_rates.frankfurter_client import FXRateService
from services.fx_rates.fx_rate_agent import FXRateAgent
from services.fx_rates.fx_rate_models import InMemoryRateStore


def _mock_http_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


# ── schedule_daily_fetch ───────────────────────────────────────────────────


def test_schedule_daily_fetch_returns_summary() -> None:
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165, "USD": 1.234}}
    with patch("httpx.get", return_value=_mock_http_response(mock_data)):
        agent = FXRateAgent()
        result = agent.schedule_daily_fetch(["GBP"])
    assert "fetched" in result
    assert "failed" in result
    assert "timestamp" in result


def test_schedule_daily_fetch_gbp() -> None:
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_http_response(mock_data)):
        agent = FXRateAgent()
        result = agent.schedule_daily_fetch(["GBP"])
    assert "GBP" in result["fetched"]


def test_schedule_daily_fetch_default_currencies() -> None:
    mock_data = {"date": "2026-01-01", "rates": {"USD": 1.234}}
    with patch("httpx.get", return_value=_mock_http_response(mock_data)):
        agent = FXRateAgent()
        result = agent.schedule_daily_fetch()  # uses DEFAULT_BASE_CURRENCIES
    # Should attempt GBP, EUR, USD
    assert len(result["fetched"]) + len(result["failed"]) == 3


def test_schedule_daily_fetch_appends_to_store() -> None:
    """I-24: schedule_daily_fetch must append entries."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_http_response(mock_data)):
        from services.fx_rates.frankfurter_client import FrankfurterClient

        client = FrankfurterClient(store=store)
        svc = FXRateService(client=client, store=store)
        agent = FXRateAgent(service=svc)
        agent.schedule_daily_fetch(["GBP"])
    assert len(store.list_recent(100)) > initial


def test_schedule_daily_fetch_failure_captured() -> None:
    """Failed fetches are captured, not raised."""
    import httpx

    store = InMemoryRateStore()
    svc = FXRateService(store=store)
    agent = FXRateAgent(service=svc)

    with patch(
        "httpx.get",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        result = agent.schedule_daily_fetch(["GBP"])

    assert "GBP" in [f["base"] for f in result["failed"]]
    assert result["fetched"] == []


def test_schedule_daily_fetch_timestamp_format() -> None:
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_http_response(mock_data)):
        agent = FXRateAgent()
        result = agent.schedule_daily_fetch(["GBP"])
    assert "T" in result["timestamp"]  # ISO format


def test_schedule_daily_fetch_partial_failure() -> None:
    """Some currencies succeed, some fail."""
    import httpx

    store = InMemoryRateStore()

    call_count = [0]

    def _side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            mock = MagicMock()
            mock.json.return_value = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
            mock.raise_for_status = MagicMock()
            return mock
        raise httpx.ConnectError("Connection refused")

    from services.fx_rates.frankfurter_client import FrankfurterClient

    client = FrankfurterClient(store=store)
    svc = FXRateService(client=client, store=store)
    agent = FXRateAgent(service=svc)

    with patch("httpx.get", side_effect=_side_effect):
        result = agent.schedule_daily_fetch(["GBP", "EUR"])

    assert len(result["fetched"]) == 1
    assert len(result["failed"]) == 1


# ── override_rate (I-27 HITL) ─────────────────────────────────────────────


def test_override_rate_returns_hitl_proposal() -> None:
    """I-27: override_rate must return HITLProposal."""
    agent = FXRateAgent()
    proposal = agent.override_rate("GBP", "EUR", Decimal("1.20"), "treasury@banxe.com", "Test")
    assert proposal["proposal_type"] == "HITL_REQUIRED"


def test_override_rate_l4_autonomy() -> None:
    agent = FXRateAgent()
    proposal = agent.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert proposal["autonomy_level"] == "L4"


def test_override_rate_treasury_officer() -> None:
    """I-27: override must require TREASURY_OFFICER."""
    agent = FXRateAgent()
    proposal = agent.override_rate("GBP", "USD", Decimal("1.25"), "ops@banxe.com", "Reason")
    assert proposal["requires_approval_from"] == "TREASURY_OFFICER"


def test_override_rate_action_field() -> None:
    agent = FXRateAgent()
    proposal = agent.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert proposal["action"] == "rate_override"


def test_override_rate_data_has_base_symbol_rate() -> None:
    agent = FXRateAgent()
    proposal = agent.override_rate("GBP", "EUR", Decimal("1.22"), "ops@banxe.com", "Reason")
    assert proposal["data"]["base"] == "GBP"
    assert proposal["data"]["symbol"] == "EUR"
    assert proposal["data"]["rate"] == "1.22"


# ── get_rate_dashboard ─────────────────────────────────────────────────────


def test_get_rate_dashboard_structure() -> None:
    agent = FXRateAgent()
    dashboard = agent.get_rate_dashboard()
    assert "cached_bases" in dashboard
    assert "entries_count" in dashboard
    assert "details" in dashboard
    assert "generated_at" in dashboard


def test_get_rate_dashboard_has_gbp() -> None:
    agent = FXRateAgent()
    dashboard = agent.get_rate_dashboard()
    assert "GBP" in dashboard["cached_bases"]


def test_get_rate_dashboard_entries_count_positive() -> None:
    agent = FXRateAgent()
    dashboard = agent.get_rate_dashboard()
    assert dashboard["entries_count"] >= 2  # seeded entries


def test_get_rate_dashboard_generated_at_iso() -> None:
    agent = FXRateAgent()
    dashboard = agent.get_rate_dashboard()
    assert "T" in dashboard["generated_at"]
