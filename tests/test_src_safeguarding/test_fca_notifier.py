"""Tests for FCA breach notification port and adapters.

Coverage:
  - FcaNotificationPayload construction (Decimal I-01)
  - InMemoryFcaNotifier — records, clears
  - N8nFcaBreachNotifier — dispatches to n8n, handles missing URL, handles HTTP errors
  - BreachDetector.notify_fca() — dry_run, no-notifier fallback, notifier path
  - SafeguardingAgent — fca_notifier wired through ports (integration path)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from src.safeguarding.breach_detector import BreachAlert, BreachDetector, BreachSeverity
from src.safeguarding.fca_notifier import (
    FcaNotificationPayload,
    FcaNotificationPort,
    InMemoryFcaNotifier,
    N8nFcaBreachNotifier,
)

D = date(2026, 6, 26)
NOW = datetime(2026, 6, 26, 9, 0, 0, tzinfo=UTC)


def _make_critical_alert(shortfall: Decimal | None = Decimal("5000.00")) -> BreachAlert:
    return BreachAlert(
        breach_date=D,
        severity=BreachSeverity.CRITICAL,
        consecutive_days=3,
        shortfall_gbp=shortfall,
        description="SAFEGUARDING SHORTFALL: test",
        fca_notification_required=True,
        raised_at=NOW,
    )


def _make_minor_alert() -> BreachAlert:
    return BreachAlert(
        breach_date=D,
        severity=BreachSeverity.MINOR,
        consecutive_days=1,
        shortfall_gbp=None,
        description="Recon break day 1",
        fca_notification_required=False,
        raised_at=NOW,
    )


# ── FcaNotificationPayload ────────────────────────────────────────────────────


class TestFcaNotificationPayload:
    def test_shortfall_is_decimal(self):
        payload = FcaNotificationPayload(
            reference="BREACH-2026-06-26-CRITICAL",
            severity="CRITICAL",
            consecutive_days=3,
            shortfall_gbp=Decimal("5000.00"),
            description="test",
            breach_date=D,
            raised_at=NOW,
        )
        assert isinstance(payload.shortfall_gbp, Decimal)

    def test_none_shortfall_allowed(self):
        payload = FcaNotificationPayload(
            reference="BREACH-2026-06-26-MAJOR",
            severity="MAJOR",
            consecutive_days=3,
            shortfall_gbp=None,
            description="streak breach",
            breach_date=D,
            raised_at=NOW,
        )
        assert payload.shortfall_gbp is None

    def test_frozen_immutable(self):
        payload = FcaNotificationPayload(
            reference="ref",
            severity="MINOR",
            consecutive_days=1,
            shortfall_gbp=None,
            description="d",
            breach_date=D,
            raised_at=NOW,
        )
        with pytest.raises(
            AttributeError
        ):  # frozen dataclass raises FrozenInstanceError (subclass)
            payload.reference = "modified"  # type: ignore[misc]


# ── FcaNotificationPort protocol ──────────────────────────────────────────────


class TestFcaNotificationPortProtocol:
    def test_in_memory_satisfies_protocol(self):
        notifier = InMemoryFcaNotifier()
        assert isinstance(notifier, FcaNotificationPort)

    def test_n8n_notifier_satisfies_protocol(self):
        notifier = N8nFcaBreachNotifier(webhook_url="http://n8n:5678/webhook/test")
        assert isinstance(notifier, FcaNotificationPort)


# ── InMemoryFcaNotifier ───────────────────────────────────────────────────────


class TestInMemoryFcaNotifier:
    def _make_payload(self) -> FcaNotificationPayload:
        return FcaNotificationPayload(
            reference="BREACH-2026-06-26-CRITICAL",
            severity="CRITICAL",
            consecutive_days=3,
            shortfall_gbp=Decimal("5000.00"),
            description="test breach",
            breach_date=D,
            raised_at=NOW,
        )

    def test_notify_records_payload(self):
        notifier = InMemoryFcaNotifier()
        payload = self._make_payload()
        notifier.notify(payload)
        assert len(notifier.notifications) == 1
        assert notifier.notifications[0].reference == "BREACH-2026-06-26-CRITICAL"

    def test_multiple_notifications_accumulate(self):
        notifier = InMemoryFcaNotifier()
        notifier.notify(self._make_payload())
        notifier.notify(self._make_payload())
        assert len(notifier.notifications) == 2

    def test_clear_empties_list(self):
        notifier = InMemoryFcaNotifier()
        notifier.notify(self._make_payload())
        notifier.clear()
        assert len(notifier.notifications) == 0

    def test_shortfall_preserved_as_decimal(self):
        notifier = InMemoryFcaNotifier()
        notifier.notify(self._make_payload())
        assert isinstance(notifier.notifications[0].shortfall_gbp, Decimal)


# ── N8nFcaBreachNotifier ──────────────────────────────────────────────────────


class TestN8nFcaBreachNotifier:
    def _make_payload(self) -> FcaNotificationPayload:
        return FcaNotificationPayload(
            reference="BREACH-2026-06-26-CRITICAL",
            severity="CRITICAL",
            consecutive_days=3,
            shortfall_gbp=Decimal("5000.00"),
            description="test",
            breach_date=D,
            raised_at=NOW,
        )

    def test_missing_url_logs_error_does_not_raise(self, monkeypatch):
        monkeypatch.delenv("N8N_FCA_WEBHOOK_URL", raising=False)
        notifier = N8nFcaBreachNotifier(webhook_url="")
        notifier.notify(self._make_payload())  # must not raise

    def test_successful_post_dispatches(self, monkeypatch):
        monkeypatch.setenv("N8N_FCA_WEBHOOK_URL", "")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response) as mock_post:
            notifier = N8nFcaBreachNotifier(webhook_url="http://n8n:5678/webhook/fca-breach-alert")
            notifier.notify(self._make_payload())

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["reference"] == "BREACH-2026-06-26-CRITICAL"
        assert call_kwargs[1]["json"]["severity"] == "CRITICAL"
        assert call_kwargs[1]["json"]["shortfall_gbp"] == "5000.00"

    def test_http_error_does_not_raise(self):
        import httpx

        with patch(
            "httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            notifier = N8nFcaBreachNotifier(webhook_url="http://n8n:5678/webhook/test")
            notifier.notify(self._make_payload())  # must not raise

    def test_post_body_uses_decimal_string_not_float(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_response) as mock_post:
            notifier = N8nFcaBreachNotifier(webhook_url="http://n8n:5678/webhook/test")
            notifier.notify(self._make_payload())

        body = mock_post.call_args[1]["json"]
        # shortfall_gbp must be a string (DecimalString), not float
        assert isinstance(body["shortfall_gbp"], str)
        assert body["shortfall_gbp"] == "5000.00"


# ── BreachDetector.notify_fca integration ────────────────────────────────────


class TestBreachDetectorNotifyFca:
    def test_dry_run_suppresses_dispatch(self):
        notifier = InMemoryFcaNotifier()
        alert = _make_critical_alert()
        detector = BreachDetector()
        detector.notify_fca(alert, dry_run=True, notifier=notifier)
        assert len(notifier.notifications) == 0

    def test_fca_not_required_skips_dispatch(self):
        notifier = InMemoryFcaNotifier()
        alert = _make_minor_alert()
        detector = BreachDetector()
        detector.notify_fca(alert, dry_run=False, notifier=notifier)
        assert len(notifier.notifications) == 0

    def test_critical_alert_dispatches_to_notifier(self):
        notifier = InMemoryFcaNotifier()
        alert = _make_critical_alert()
        detector = BreachDetector()
        detector.notify_fca(alert, dry_run=False, notifier=notifier)
        assert len(notifier.notifications) == 1
        assert notifier.notifications[0].severity == "CRITICAL"

    def test_no_notifier_logs_only_does_not_raise(self):
        alert = _make_critical_alert()
        detector = BreachDetector()
        detector.notify_fca(alert, dry_run=False, notifier=None)  # must not raise

    def test_payload_shortfall_is_decimal(self):
        notifier = InMemoryFcaNotifier()
        alert = _make_critical_alert(shortfall=Decimal("9999.99"))
        detector = BreachDetector()
        detector.notify_fca(alert, dry_run=False, notifier=notifier)
        assert notifier.notifications[0].shortfall_gbp == Decimal("9999.99")
        assert isinstance(notifier.notifications[0].shortfall_gbp, Decimal)

    def test_none_shortfall_passed_through(self):
        notifier = InMemoryFcaNotifier()
        # streak-only breach (no monetary shortfall but still critical)
        alert = _make_critical_alert(shortfall=None)
        detector = BreachDetector()
        detector.notify_fca(alert, dry_run=False, notifier=notifier)
        assert notifier.notifications[0].shortfall_gbp is None
