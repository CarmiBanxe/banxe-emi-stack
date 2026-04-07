"""
test_breach_detector.py — Unit tests for BreachDetector
IL-015 Step 4 | FCA CASS 15.12 | banxe-emi-stack

Covers:
  - No breach when streak < BREACH_DAYS
  - No breach when discrepancy below amount threshold
  - Breach recorded when streak >= BREACH_DAYS + amount >= threshold
  - write_breach() called exactly once per qualifying account
  - n8n alert fired (mock httpx)
  - Multiple accounts: only qualifying ones escalated
  - InMemoryReconClient.breaches property
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch


# ── minimal ReconResult stub (mirrors reconciliation_engine.ReconResult) ──────

@dataclass(frozen=True)
class _ReconResult:
    account_id: str
    account_type: str
    currency: str
    discrepancy: Decimal
    status: str
    recon_date: date = date(2026, 4, 7)
    internal_balance: Decimal = Decimal("0")
    external_balance: Decimal = Decimal("0")
    source_file: str = ""
    alert_sent: bool = False


# ── InMemoryBreachClient stub ─────────────────────────────────────────────────

class InMemoryBreachClient:
    """Minimal stub implementing BreachClientProtocol for tests."""

    def __init__(self, streak_map: dict | None = None) -> None:
        self._streak_map = streak_map or {}   # account_id → streak count
        self.breaches_written: list = []
        self.latest_disc: dict = {}

    def get_discrepancy_streak(self, account_id: str, as_of: date, min_days: int) -> int:
        return self._streak_map.get(account_id, 0)

    def write_breach(self, breach) -> None:
        self.breaches_written.append(breach)

    def get_latest_discrepancy(self, account_id: str, as_of: date):
        return self.latest_disc.get(account_id)


# ── tests ─────────────────────────────────────────────────────────────────────

from services.recon.breach_detector import BreachDetector, BreachRecord  # noqa: E402


class TestBreachDetectorNoBreachCases:

    def test_no_breach_when_streak_below_threshold(self):
        """DISCREPANCY for 2 days (< 3) → no breach written."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 2})
        detector = BreachDetector(ch, breach_days=3)
        result = _ReconResult(
            account_id="acct-1", account_type="operational",
            currency="GBP", discrepancy=Decimal("500.00"), status="DISCREPANCY",
        )
        breaches = detector.check_and_escalate([result], date(2026, 4, 7))
        assert breaches == []
        assert ch.breaches_written == []

    def test_no_breach_when_status_matched(self):
        """MATCHED accounts never trigger breach."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 10})
        detector = BreachDetector(ch, breach_days=3)
        result = _ReconResult(
            account_id="acct-1", account_type="operational",
            currency="GBP", discrepancy=Decimal("0"), status="MATCHED",
        )
        breaches = detector.check_and_escalate([result], date(2026, 4, 7))
        assert breaches == []

    def test_no_breach_when_discrepancy_below_amount_threshold(self):
        """Streak = 5 days but £5 < £10 threshold → no breach."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 5})
        detector = BreachDetector(
            ch, breach_days=3, amount_threshold=Decimal("10.00")
        )
        result = _ReconResult(
            account_id="acct-1", account_type="operational",
            currency="GBP", discrepancy=Decimal("5.00"), status="DISCREPANCY",
        )
        breaches = detector.check_and_escalate([result], date(2026, 4, 7))
        assert breaches == []

    def test_no_breach_when_pending(self):
        """PENDING accounts are never assessed for breach."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 10})
        detector = BreachDetector(ch, breach_days=3)
        result = _ReconResult(
            account_id="acct-1", account_type="operational",
            currency="GBP", discrepancy=Decimal("0"), status="PENDING",
        )
        breaches = detector.check_and_escalate([result], date(2026, 4, 7))
        assert breaches == []


class TestBreachDetectorBreachTriggered:

    def _make_discrepancy(self, account_id="acct-1", amount="500.00"):
        return _ReconResult(
            account_id=account_id, account_type="client_funds",
            currency="GBP", discrepancy=Decimal(amount), status="DISCREPANCY",
        )

    def test_breach_written_when_streak_meets_threshold(self):
        """Streak = 3, discrepancy = £500 → breach written."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 3})
        detector = BreachDetector(ch, breach_days=3, amount_threshold=Decimal("10.00"))
        with patch("services.recon.breach_detector.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            breaches = detector.check_and_escalate(
                [self._make_discrepancy()], date(2026, 4, 7)
            )
        assert len(breaches) == 1
        assert len(ch.breaches_written) == 1

    def test_breach_record_fields(self):
        """BreachRecord has correct fields."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 4})
        detector = BreachDetector(ch, breach_days=3, amount_threshold=Decimal("10.00"))
        with patch("services.recon.breach_detector.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            breaches = detector.check_and_escalate(
                [self._make_discrepancy(amount="750.00")], date(2026, 4, 9)
            )
        b = breaches[0]
        assert b.account_id == "acct-1"
        assert b.account_type == "client_funds"
        assert b.discrepancy == Decimal("750.00")
        assert b.days_outstanding == 4
        assert b.latest_date == date(2026, 4, 9)
        assert isinstance(b, BreachRecord)

    def test_multiple_accounts_only_qualifying_breach(self):
        """Two accounts: one qualifies (streak=3), one doesn't (streak=1)."""
        ch = InMemoryBreachClient(streak_map={"acct-1": 3, "acct-2": 1})
        detector = BreachDetector(ch, breach_days=3, amount_threshold=Decimal("10.00"))
        results = [
            self._make_discrepancy("acct-1", "200.00"),
            self._make_discrepancy("acct-2", "150.00"),
        ]
        with patch("services.recon.breach_detector.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            breaches = detector.check_and_escalate(results, date(2026, 4, 7))
        assert len(breaches) == 1
        assert breaches[0].account_id == "acct-1"

    def test_n8n_webhook_called_when_url_set(self, monkeypatch):
        """FCA alert fires n8n POST when N8N_WEBHOOK_URL is set."""
        monkeypatch.setenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/fca-breach")
        ch = InMemoryBreachClient(streak_map={"acct-1": 3})
        with patch("services.recon.breach_detector.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            import importlib
            import services.recon.breach_detector as bd
            importlib.reload(bd)
            detector = bd.BreachDetector(ch, breach_days=3, amount_threshold=Decimal("10.00"))
            detector.check_and_escalate([self._make_discrepancy()], date(2026, 4, 7))
        assert mock_post.called

    def test_n8n_not_called_when_url_empty(self, monkeypatch):
        """No n8n call when N8N_WEBHOOK_URL is empty (graceful degradation)."""
        monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
        ch = InMemoryBreachClient(streak_map={"acct-1": 3})
        with patch("services.recon.breach_detector.httpx.post") as mock_post:
            with patch("services.recon.breach_detector.N8N_WEBHOOK_URL", ""):
                detector = BreachDetector(ch, breach_days=3, amount_threshold=Decimal("10.00"))
                detector.check_and_escalate([self._make_discrepancy()], date(2026, 4, 7))
        mock_post.assert_not_called()

    def test_n8n_failure_does_not_raise(self, monkeypatch):
        """n8n POST failure → logged, NOT propagated (breach still written)."""
        monkeypatch.setenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/test")
        ch = InMemoryBreachClient(streak_map={"acct-1": 3})
        import httpx as _httpx
        with patch("services.recon.breach_detector.httpx.post", side_effect=_httpx.ConnectError("refused")):
            with patch("services.recon.breach_detector.N8N_WEBHOOK_URL", "http://localhost:5678/webhook/test"):
                detector = BreachDetector(ch, breach_days=3, amount_threshold=Decimal("10.00"))
                breaches = detector.check_and_escalate([self._make_discrepancy()], date(2026, 4, 7))
        # breach still written even though n8n failed
        assert len(breaches) == 1
        assert len(ch.breaches_written) == 1


class TestInMemoryReconClientBreaches:

    def test_breaches_property_empty_initially(self):
        from services.recon.clickhouse_client import InMemoryReconClient
        ch = InMemoryReconClient()
        assert ch.breaches == []

    def test_write_breach_captured(self):
        from services.recon.clickhouse_client import InMemoryReconClient
        ch = InMemoryReconClient()
        breach = BreachRecord(
            account_id="acct-1", account_type="operational",
            currency="GBP", discrepancy=Decimal("200.00"),
            days_outstanding=3, first_seen=date(2026, 4, 5), latest_date=date(2026, 4, 7),
        )
        ch.write_breach(breach)
        assert len(ch.breaches) == 1
        assert ch.breaches[0]["account_id"] == "acct-1"
        assert ch.breaches[0]["days_outstanding"] == 3
