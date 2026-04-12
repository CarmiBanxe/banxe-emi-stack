"""Tests for FCARegDataClient — MockFCARegDataClient and NotificationResult."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.recon.breach_detector import BreachRecord
from services.recon.fca_regdata_client import (
    FCARegDataClient,
    MockFCARegDataClient,
    NotificationResult,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


def make_breach(
    account_id: str = "019d6332-f274-709a-b3a7-983bc8745886",
    discrepancy: str = "15000.00",
    days: int = 4,
) -> BreachRecord:
    return BreachRecord(
        account_id=account_id,
        account_type="client_funds",
        currency="GBP",
        discrepancy=Decimal(discrepancy),
        days_outstanding=days,
        first_seen=date(2026, 4, 7),
        latest_date=date(2026, 4, 10),
    )


# ── Test: MockFCARegDataClient.submit_breach_notification returns NotificationResult ──


def test_mock_client_submit_returns_notification_result():
    """MockFCARegDataClient.submit_breach_notification returns NotificationResult with success=True."""
    client = MockFCARegDataClient()
    breach = make_breach()

    result = client.submit_breach_notification(breach)

    assert isinstance(result, NotificationResult)
    assert result.success is True
    assert len(result.fca_reference) > 0
    assert "SANDBOX" in result.fca_reference
    assert result.error is None
    assert result.submitted_at  # non-empty ISO string


def test_mock_client_records_notification():
    """MockFCARegDataClient records notification in .notifications list."""
    client = MockFCARegDataClient()
    breach = make_breach()

    client.submit_breach_notification(breach)

    assert len(client.notifications) == 1
    notif = client.notifications[0]
    assert notif["breach_account_id"] == breach.account_id
    assert notif["is_mock"] is True
    assert notif["discrepancy"] == str(breach.discrepancy)
    assert notif["days_outstanding"] == breach.days_outstanding


def test_mock_client_multiple_breaches():
    """MockFCARegDataClient records multiple breach notifications."""
    client = MockFCARegDataClient()

    for i in range(3):
        breach = make_breach(account_id=f"account-{i}")
        client.submit_breach_notification(breach)

    assert len(client.notifications) == 3


def test_mock_client_fca_reference_contains_account_fragment():
    """MockFCARegDataClient FCA reference contains account ID fragment."""
    client = MockFCARegDataClient()
    breach = make_breach(account_id="abcdef12-1234-1234-1234-123456789012")

    result = client.submit_breach_notification(breach)

    assert "ABCDEF12" in result.fca_reference


# ── Test: NotificationResult is frozen dataclass ─────────────────────────────


def test_notification_result_is_frozen():
    """NotificationResult is a frozen dataclass — cannot be mutated."""
    result = NotificationResult(
        success=True,
        fca_reference="FCA-TEST-001",
        submitted_at="2026-04-10T18:00:00Z",
    )

    with pytest.raises((AttributeError, TypeError)):
        result.success = False  # type: ignore[misc]


def test_notification_result_default_error_is_none():
    """NotificationResult.error defaults to None."""
    result = NotificationResult(
        success=True,
        fca_reference="FCA-REF",
        submitted_at="2026-04-10T18:00:00Z",
    )
    assert result.error is None


# ── Test: FCARegDataClient returns failure when API key not set ──────────────


def test_production_client_returns_failure_without_api_key(monkeypatch):
    """FCARegDataClient returns NotificationResult(success=False) when API key not configured."""
    monkeypatch.delenv("FCA_REGDATA_API_KEY", raising=False)
    monkeypatch.delenv("FCA_REGDATA_URL", raising=False)
    monkeypatch.delenv("FCA_FIRM_REFERENCE", raising=False)

    client = FCARegDataClient()
    breach = make_breach()
    result = client.submit_breach_notification(breach)

    assert result.success is False
    assert result.error is not None
    assert "FCA_REGDATA_API_KEY" in result.error


# ── Test: Protocol compliance ─────────────────────────────────────────────────


def test_mock_client_implements_protocol():
    """MockFCARegDataClient has submit_breach_notification method (protocol compliant)."""
    client = MockFCARegDataClient()
    assert hasattr(client, "submit_breach_notification")
    assert callable(client.submit_breach_notification)
