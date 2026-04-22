"""Tests for frankfurter_client.py — FrankfurterClient, FXRateService.

IL-FXR-01 | Phase 52A | Sprint 37
Uses unittest.mock.patch("httpx.get") — no real HTTP requests.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.fx_rates.frankfurter_client import (
    BLOCKED_CURRENCIES,
    FrankfurterClient,
    FXRateService,
    _safe_decimal,
)
from services.fx_rates.fx_rate_models import InMemoryRateStore, RateEntry

# ── Helpers ────────────────────────────────────────────────────────────────


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ── _safe_decimal ──────────────────────────────────────────────────────────


def test_safe_decimal_from_float() -> None:
    """I-01: _safe_decimal must convert API floats to Decimal."""
    result = _safe_decimal(1.165)
    assert isinstance(result, Decimal)


def test_safe_decimal_from_string() -> None:
    result = _safe_decimal("1.165")
    assert result == Decimal("1.165")


def test_safe_decimal_invalid_raises() -> None:
    with pytest.raises(ValueError):
        _safe_decimal("not-a-number")


def test_safe_decimal_none_raises() -> None:
    with pytest.raises(ValueError):
        _safe_decimal(None)


# ── BLOCKED_CURRENCIES (I-02) ──────────────────────────────────────────────


def test_blocked_currencies_rub() -> None:
    assert "RUB" in BLOCKED_CURRENCIES


def test_blocked_currencies_irr() -> None:
    assert "IRR" in BLOCKED_CURRENCIES


def test_blocked_currencies_kpw() -> None:
    assert "KPW" in BLOCKED_CURRENCIES


def test_blocked_currencies_byn() -> None:
    assert "BYN" in BLOCKED_CURRENCIES


def test_eur_not_blocked() -> None:
    assert "EUR" not in BLOCKED_CURRENCIES


# ── FrankfurterClient.get_latest ───────────────────────────────────────────


def test_get_latest_returns_decimal_rates() -> None:
    """I-01: get_latest must return {symbol: Decimal}."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165, "USD": 1.234}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        rates = client.get_latest(base="GBP")

    assert isinstance(rates["EUR"], Decimal)
    assert isinstance(rates["USD"], Decimal)


def test_get_latest_appends_to_store() -> None:
    """I-24: get_latest must append to store."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        client.get_latest(base="GBP")

    assert len(store.list_recent(100)) == initial + 1


def test_get_latest_filters_blocked_currencies() -> None:
    """I-02: Blocked currencies must not appear in results."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165, "RUB": 100.0, "IRR": 42000.0}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        rates = client.get_latest(base="GBP")

    assert "RUB" not in rates
    assert "IRR" not in rates
    assert "EUR" in rates


def test_get_latest_with_symbols_filter() -> None:
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}

    with patch("httpx.get", return_value=_mock_response(mock_data)) as mock_get:
        client.get_latest(base="GBP", symbols=["EUR"])

    call_kwargs = mock_get.call_args
    assert call_kwargs is not None


def test_get_latest_symbols_blocked_filtered_from_params() -> None:
    """I-02: Blocked symbols must not be sent to API."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}

    with patch("httpx.get", return_value=_mock_response(mock_data)) as mock_get:
        client.get_latest(base="GBP", symbols=["EUR", "RUB"])

    # RUB should be filtered from the symbols param
    call_kwargs = mock_get.call_args
    params = call_kwargs[1].get("params", {}) if call_kwargs[1] else {}
    if "symbols" in params:
        assert "RUB" not in params["symbols"]


# ── FrankfurterClient.get_historical ──────────────────────────────────────


def test_get_historical_returns_decimal() -> None:
    """I-01: historical rates must be Decimal."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.160}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        rates = client.get_historical("2026-01-01", base="GBP")

    assert isinstance(rates.get("EUR"), Decimal)


def test_get_historical_appends_to_store() -> None:
    """I-24: historical fetch must append."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2025-06-01", "rates": {"EUR": 1.15}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        client.get_historical("2025-06-01", base="GBP")

    assert len(store.list_recent(100)) == initial + 1


def test_get_historical_blocked_filtered() -> None:
    """I-02: Blocked currencies filtered from historical."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2025-06-01", "rates": {"EUR": 1.15, "BYN": 3.5}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        rates = client.get_historical("2025-06-01", base="GBP")

    assert "BYN" not in rates
    assert "EUR" in rates


# ── FrankfurterClient.get_time_series ─────────────────────────────────────


def test_get_time_series_returns_rate_entries() -> None:
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {
        "rates": {
            "2026-01-01": {"EUR": 1.165},
            "2026-01-02": {"EUR": 1.168},
        }
    }

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        entries = client.get_time_series("2026-01-01", "2026-01-02", base="GBP")

    assert len(entries) == 2
    assert all(isinstance(e, RateEntry) for e in entries)


def test_get_time_series_appends_all() -> None:
    """I-24: All time series entries appended."""
    store = InMemoryRateStore()
    initial = len(store.list_recent(100))
    client = FrankfurterClient(store=store)
    mock_data = {
        "rates": {
            "2026-01-01": {"EUR": 1.165},
            "2026-01-02": {"EUR": 1.168},
            "2026-01-03": {"EUR": 1.170},
        }
    }

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        client.get_time_series("2026-01-01", "2026-01-03", base="GBP")

    assert len(store.list_recent(100)) == initial + 3


# ── FrankfurterClient.convert ─────────────────────────────────────────────


def test_convert_returns_decimal_amounts() -> None:
    """I-01: convert must return ConversionResult with Decimal amounts."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        result = client.convert(Decimal("100.00"), "GBP", "EUR")

    assert isinstance(result.amount, Decimal)
    assert isinstance(result.converted_amount, Decimal)
    assert isinstance(result.rate, Decimal)


def test_convert_correct_calculation() -> None:
    """I-01: 100 GBP × 1.165 = 116.5000 EUR."""
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {"EUR": 1.165}}

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        result = client.convert(Decimal("100.00"), "GBP", "EUR")

    assert result.converted_amount == Decimal("116.5000")


def test_convert_blocked_from_currency_raises() -> None:
    """I-02: Convert from blocked currency must raise ValueError."""
    client = FrankfurterClient()
    with pytest.raises(ValueError, match="I-02"):
        client.convert(Decimal("100"), "RUB", "EUR")


def test_convert_blocked_to_currency_raises() -> None:
    """I-02: Convert to blocked currency must raise ValueError."""
    client = FrankfurterClient()
    with pytest.raises(ValueError, match="I-02"):
        client.convert(Decimal("100"), "GBP", "IRR")


def test_convert_unavailable_rate_raises() -> None:
    store = InMemoryRateStore()
    client = FrankfurterClient(store=store)
    mock_data = {"date": "2026-01-01", "rates": {}}  # no EUR

    with patch("httpx.get", return_value=_mock_response(mock_data)):
        with pytest.raises(ValueError, match="Rate not available"):
            client.convert(Decimal("100"), "GBP", "EUR")


# ── FXRateService ─────────────────────────────────────────────────────────


def test_fx_rate_service_override_hitl_proposal() -> None:
    """I-27: override_rate must return HITLProposal."""
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Test")
    assert proposal["proposal_type"] == "HITL_REQUIRED"
    assert proposal["requires_approval_from"] == "TREASURY_OFFICER"
    assert proposal["autonomy_level"] == "L4"


def test_fx_rate_service_override_contains_override_id() -> None:
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.20"), "ops@banxe.com", "Reason")
    assert "override_id" in proposal
    assert proposal["override_id"].startswith("ovr_")


def test_fx_rate_service_get_cached_latest() -> None:
    svc = FXRateService()
    entry = svc.get_cached_latest("GBP")
    assert entry is not None
    assert entry.base == "GBP"


def test_fx_rate_service_get_cached_missing_returns_none() -> None:
    svc = FXRateService()
    result = svc.get_cached_latest("XYZ_MISSING")
    assert result is None


def test_fx_rate_service_override_rate_is_string_in_data() -> None:
    """I-01: Rate in HITL proposal data should be a string."""
    svc = FXRateService()
    proposal = svc.override_rate("GBP", "EUR", Decimal("1.25"), "ops@banxe.com", "Reason")
    assert isinstance(proposal["data"]["rate"], str)
