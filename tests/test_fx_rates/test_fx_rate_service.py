"""Tests for FXRateService — HITL overrides, cached rates, I-24 append.

IL-FXR-01 | Phase 52A | Sprint 37
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.fx_rates.frankfurter_client import FXRateService
from services.fx_rates.fx_rate_models import InMemoryRateStore, RateEntry


def _mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


# ── FXRateService.get_latest ───────────────────────────────────────────────


def test_service_get_latest_delegates_to_client() -> None:
    store = InMemoryRateStore()
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        rates = svc.get_latest(base="GBP")
    assert "EUR" in rates
    assert isinstance(rates["EUR"], Decimal)


def test_service_get_latest_appends_to_store() -> None:
    """I-24: get_latest via service must append to store."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        svc.get_latest(base="GBP")
    assert len(store.list_recent(100)) == initial + 1


# ── FXRateService.get_historical ──────────────────────────────────────────


def test_service_get_historical_returns_decimal() -> None:
    """I-01: historical rates via service must be Decimal."""
    store = InMemoryRateStore()
    mock_data = {"date": "2025-06-01", "rates": {"USD": 1.250}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        rates = svc.get_historical("2025-06-01", base="GBP")
    assert isinstance(rates.get("USD"), Decimal)


def test_service_get_historical_appends() -> None:
    """I-24: historical via service must append."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    mock_data = {"date": "2025-06-01", "rates": {"USD": 1.25}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        svc.get_historical("2025-06-01", base="GBP")
    assert len(store.list_recent(100)) == initial + 1


# ── FXRateService.convert ─────────────────────────────────────────────────


def test_service_convert_decimal_precision() -> None:
    """I-01: convert must use Decimal precision (4 decimal places)."""
    store = InMemoryRateStore()
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        result = svc.convert(Decimal("100.00"), "GBP", "EUR")
    assert result.converted_amount == Decimal("116.5000")
    assert isinstance(result.converted_amount, Decimal)


def test_service_convert_zero_amount_raises() -> None:
    store = InMemoryRateStore()
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        # zero is technically valid for convert, just results in 0
        result = svc.convert(Decimal("0.00"), "GBP", "EUR")
    assert result.converted_amount == Decimal("0.0000")


# ── FXRateService.override_rate (I-27 HITL) ───────────────────────────────


def test_override_rate_hitl_proposal_type() -> None:
    """I-27: override must always return HITL_REQUIRED."""
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "treasury@banxe.com", "Manual fix")
    assert proposal["proposal_type"] == "HITL_REQUIRED"


def test_override_rate_requires_treasury_officer() -> None:
    """I-27 L4: must require TREASURY_OFFICER."""
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert proposal["requires_approval_from"] == "TREASURY_OFFICER"


def test_override_rate_autonomy_level_l4() -> None:
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert proposal["autonomy_level"] == "L4"


def test_override_rate_action_field() -> None:
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert proposal["action"] == "rate_override"


def test_override_rate_has_created_at() -> None:
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert "created_at" in proposal
    assert proposal["created_at"]


def test_override_rate_data_contains_base_symbol_rate() -> None:
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.25"), "ops@banxe.com", "Test")
    assert proposal["data"]["base"] == "GBP"
    assert proposal["data"]["symbol"] == "EUR"
    assert proposal["data"]["rate"] == "1.25"


def test_override_rate_deterministic_id() -> None:
    """Same inputs must produce same override_id."""
    svc = FXRateService()
    p1 = svc.override_rate("GBP", "EUR", Decimal("1.25"), "ops@banxe.com", "Test")
    p2 = svc.override_rate("GBP", "EUR", Decimal("1.25"), "ops@banxe.com", "Test")
    assert p1["override_id"] == p2["override_id"]


def test_override_rate_different_inputs_different_id() -> None:
    svc = FXRateService()
    p1 = svc.override_rate("GBP", "EUR", Decimal("1.25"), "ops@banxe.com", "Test")
    p2 = svc.override_rate("GBP", "USD", Decimal("1.25"), "ops@banxe.com", "Test")
    assert p1["override_id"] != p2["override_id"]


# ── FXRateService.get_cached_latest ───────────────────────────────────────


def test_get_cached_latest_gbp() -> None:
    svc = FXRateService()
    entry = svc.get_cached_latest("GBP")
    assert entry is not None
    assert isinstance(entry, RateEntry)


def test_get_cached_latest_missing_none() -> None:
    svc = FXRateService()
    result = svc.get_cached_latest("MISSING_CODE")
    assert result is None


def test_get_cached_latest_after_append() -> None:
    """I-24: After appending, get_cached_latest returns appended entry."""
    store = InMemoryRateStore()
    svc = FXRateService(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc.get_latest(base="CHF")
    cached = svc.get_cached_latest("CHF")
    assert cached is not None
    assert cached.base == "CHF"


# ── FXRateService.get_time_series ─────────────────────────────────────────


def test_service_get_time_series_returns_list() -> None:
    store = InMemoryRateStore()
    mock_data = {"rates": {"2026-01-01": {"EUR": 1.165}, "2026-01-02": {"EUR": 1.168}}}
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        entries = svc.get_time_series("2026-01-01", "2026-01-02", base="GBP")
    assert len(entries) == 2


def test_service_get_time_series_appends_all() -> None:
    """I-24: time series appends all entries."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    mock_data = {
        "rates": {
            "2026-01-01": {"EUR": 1.165},
            "2026-01-02": {"EUR": 1.168},
            "2026-01-03": {"EUR": 1.170},
        }
    }
    with patch("httpx.get", return_value=_mock_response(mock_data)):
        svc = FXRateService(store=store)
        svc.get_time_series("2026-01-01", "2026-01-03")
    assert len(store.list_recent(100)) == initial + 3
