"""
tests/test_recon_breach_notify.py
Tests for BreachNotifyPort — D-recon spec §4 (IL-CBS-DRECON-BREACHNOTIFY-2026-06-26).

Coverage:
  - BreachEvent frozen dataclass: immutability, I-01 Decimal fields
  - InMemoryBreachNotifyPort: Protocol compliance, accumulates events, ordered
  - N8nBreachNotifyAdapter: Protocol compliance, sends POST, payload shape
  - N8nBreachNotifyAdapter: fail-open on HTTP error, connection error, timeout
  - N8nBreachNotifyAdapter: no-op + warning when URL not set
  - ReconciliationEngine: calls breach_notifier on SHORTFALL only
  - ReconciliationEngine: breach_notifier=None → no error (backward-compat)
  - ReconciliationEngine: BreachEvent fields match recon output
  - ReconciliationEngine: multiple runs, each shortfall emits one event
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.recon.breach_notify_port import (
    BreachEvent,
    BreachNotifyPort,
    InMemoryBreachNotifyPort,
    N8nBreachNotifyAdapter,
)
from services.recon.recon_engine import ReconciliationEngine
from services.recon.recon_port import InMemoryLedgerPort

# ── Fixtures ──────────────────────────────────────────────────────────────────

RECON_DATE = "2026-06-26"


def _make_event(
    recon_id: str = "recon-abc123",
    shortfall: Decimal = Decimal("500.00"),
) -> BreachEvent:
    return BreachEvent(
        event_type="safeguarding.breach.detected",
        recon_id=recon_id,
        recon_date=RECON_DATE,
        currency="GBP",
        client_funds_total=Decimal("10500.00"),
        safeguarding_total=Decimal("10000.00"),
        shortfall=shortfall,
        detected_at="2026-06-26T00:00:00+00:00",
        requires_approval_from="MLRO",
    )


def _mock_ok_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


def _mock_error_response(status: int = 500) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock(side_effect=Exception(f"HTTP {status}"))
    return resp


# ── BreachEvent ───────────────────────────────────────────────────────────────


class TestBreachEvent:
    def test_is_frozen(self) -> None:
        event = _make_event()
        with pytest.raises((AttributeError, TypeError)):
            event.recon_id = "other"  # type: ignore[misc]

    def test_shortfall_is_decimal(self) -> None:
        event = _make_event(shortfall=Decimal("1234.56"))
        assert isinstance(event.shortfall, Decimal)

    def test_client_funds_total_is_decimal(self) -> None:
        assert isinstance(_make_event().client_funds_total, Decimal)

    def test_safeguarding_total_is_decimal(self) -> None:
        assert isinstance(_make_event().safeguarding_total, Decimal)

    def test_event_type_constant(self) -> None:
        assert _make_event().event_type == "safeguarding.breach.detected"

    def test_requires_approval_from_default(self) -> None:
        assert _make_event().requires_approval_from == "MLRO"


# ── InMemoryBreachNotifyPort ──────────────────────────────────────────────────


class TestInMemoryBreachNotifyPort:
    def test_satisfies_protocol(self) -> None:
        port = InMemoryBreachNotifyPort()
        assert isinstance(port, BreachNotifyPort)

    def test_starts_empty(self) -> None:
        port = InMemoryBreachNotifyPort()
        assert port.events == []

    def test_records_single_event(self) -> None:
        port = InMemoryBreachNotifyPort()
        event = _make_event()
        port.notify(event)
        assert len(port.events) == 1
        assert port.events[0] is event

    def test_records_multiple_events_in_order(self) -> None:
        port = InMemoryBreachNotifyPort()
        e1 = _make_event(recon_id="recon-001", shortfall=Decimal("100"))
        e2 = _make_event(recon_id="recon-002", shortfall=Decimal("200"))
        port.notify(e1)
        port.notify(e2)
        assert port.events[0].recon_id == "recon-001"
        assert port.events[1].recon_id == "recon-002"

    def test_independent_instances_do_not_share_state(self) -> None:
        p1 = InMemoryBreachNotifyPort()
        p2 = InMemoryBreachNotifyPort()
        p1.notify(_make_event())
        assert p2.events == []


# ── N8nBreachNotifyAdapter: Protocol ─────────────────────────────────────────


class TestN8nAdapterProtocol:
    def test_satisfies_breach_notify_port(self) -> None:
        adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/webhook/test")
        assert isinstance(adapter, BreachNotifyPort)


# ── N8nBreachNotifyAdapter: happy path ───────────────────────────────────────


class TestN8nAdapterHappyPath:
    def test_sends_post_to_configured_url(self) -> None:
        with patch("httpx.post", return_value=_mock_ok_response()) as mock_post:
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event())
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://n8n:5678/test"

    def test_payload_contains_event_type(self) -> None:
        with patch("httpx.post", return_value=_mock_ok_response()) as mock_post:
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event())
            payload = mock_post.call_args[1]["json"]
            assert payload["event_type"] == "safeguarding.breach.detected"

    def test_payload_amounts_are_strings_not_floats(self) -> None:
        with patch("httpx.post", return_value=_mock_ok_response()) as mock_post:
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event(shortfall=Decimal("500.00")))
            payload = mock_post.call_args[1]["json"]
            assert isinstance(payload["shortfall"], str)
            assert isinstance(payload["client_funds_total"], str)
            assert isinstance(payload["safeguarding_total"], str)

    def test_payload_shortfall_value_correct(self) -> None:
        with patch("httpx.post", return_value=_mock_ok_response()) as mock_post:
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event(shortfall=Decimal("1234.56")))
            payload = mock_post.call_args[1]["json"]
            assert payload["shortfall"] == "1234.56"

    def test_payload_contains_recon_id(self) -> None:
        with patch("httpx.post", return_value=_mock_ok_response()) as mock_post:
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event(recon_id="recon-xyz789"))
            payload = mock_post.call_args[1]["json"]
            assert payload["recon_id"] == "recon-xyz789"


# ── N8nBreachNotifyAdapter: fail-open ────────────────────────────────────────


class TestN8nAdapterFailOpen:
    def test_http_error_does_not_raise(self) -> None:
        with patch("httpx.post", return_value=_mock_error_response(500)):
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event())  # must not raise

    def test_connection_error_does_not_raise(self) -> None:
        import httpx

        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event())  # must not raise

    def test_timeout_does_not_raise(self) -> None:
        import httpx

        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            adapter = N8nBreachNotifyAdapter(webhook_url="http://n8n:5678/test")
            adapter.notify(_make_event())  # must not raise

    def test_no_url_makes_no_http_call(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            # Ensure neither env var is set
            import os

            os.environ.pop("N8N_BREACH_NOTIFY_URL", None)
            os.environ.pop("N8N_WEBHOOK_URL", None)
            with patch("httpx.post") as mock_post:
                adapter = N8nBreachNotifyAdapter()
                adapter.notify(_make_event())
                mock_post.assert_not_called()

    def test_env_var_used_when_no_constructor_url(self) -> None:
        with patch.dict("os.environ", {"N8N_BREACH_NOTIFY_URL": "http://env-n8n:5678/breach"}):
            with patch("httpx.post", return_value=_mock_ok_response()) as mock_post:
                adapter = N8nBreachNotifyAdapter()
                adapter.notify(_make_event())
                call_url = mock_post.call_args[0][0]
                assert call_url == "http://env-n8n:5678/breach"


# ── ReconciliationEngine integration ─────────────────────────────────────────


class TestReconEngineBreachNotify:
    def _shortfall_ledger(self) -> InMemoryLedgerPort:
        ledger = InMemoryLedgerPort()
        ledger.add_client_fund("CLIENT-001", Decimal("10500.00"))
        ledger.add_safeguarding("SAFEG-001", Decimal("10000.00"))
        return ledger

    def _balanced_ledger(self) -> InMemoryLedgerPort:
        ledger = InMemoryLedgerPort()
        ledger.add_client_fund("CLIENT-001", Decimal("10000.00"))
        ledger.add_safeguarding("SAFEG-001", Decimal("10000.00"))
        return ledger

    def _surplus_ledger(self) -> InMemoryLedgerPort:
        ledger = InMemoryLedgerPort()
        ledger.add_client_fund("CLIENT-001", Decimal("9500.00"))
        ledger.add_safeguarding("SAFEG-001", Decimal("10000.00"))
        return ledger

    def test_calls_notify_on_shortfall(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert len(port.events) == 1

    def test_no_notify_on_balanced(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._balanced_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert port.events == []

    def test_no_notify_on_surplus(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._surplus_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert port.events == []

    def test_breach_event_shortfall_amount_correct(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert port.events[0].shortfall == Decimal("500.00")

    def test_breach_event_recon_id_matches_result(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        result = engine.run_daily_recon(RECON_DATE)
        assert port.events[0].recon_id == result.recon_id

    def test_breach_event_recon_date_matches_input(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert port.events[0].recon_date == RECON_DATE

    def test_breach_event_type_is_canonical(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert port.events[0].event_type == "safeguarding.breach.detected"

    def test_no_notify_port_does_not_raise(self) -> None:
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=None,
        )
        result = engine.run_daily_recon(RECON_DATE)  # must not raise
        assert result is not None

    def test_multiple_runs_each_shortfall_emits_event(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon("2026-06-25")
        engine.run_daily_recon("2026-06-26")
        assert len(port.events) == 2

    def test_breach_event_requires_approval_from_mlro(self) -> None:
        port = InMemoryBreachNotifyPort()
        engine = ReconciliationEngine(
            ledger=self._shortfall_ledger(),
            breach_notifier=port,
        )
        engine.run_daily_recon(RECON_DATE)
        assert port.events[0].requires_approval_from == "MLRO"


# ── E2E: ReconciliationEngine → GabrielBreachHandler → ReturnsGovernor ────────


class TestReconToGabrielChain:
    """Full D-recon → K-gabriel chain integration tests.

    Verifies that a CASS 15 shortfall detected by ReconciliationEngine creates a
    DRAFT SubmissionRecord in ReturnsGovernor via GabrielBreachHandler, and that
    the MLRO can approve it (I-27 HITL gate).
    """

    @staticmethod
    def _shortfall_engine(governor, registrar) -> ReconciliationEngine:
        from services.gabriel.breach_handler import GabrielBreachHandler

        handler = GabrielBreachHandler(governor=governor, registrar=registrar)
        ledger = InMemoryLedgerPort()
        ledger.add_client_fund("CLIENT-001", Decimal("50000.00"))
        ledger.add_safeguarding("SAFEG-001", Decimal("49000.00"))  # 1 000 shortfall
        return ReconciliationEngine(ledger=ledger, breach_notifier=handler)

    def test_shortfall_creates_draft_in_governor(self) -> None:
        from services.gabriel.breach_handler import InMemoryBreachRegistrar
        from services.gabriel.gabriel_models import InMemoryGabrielAuditPort
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        engine = self._shortfall_engine(gov, reg)
        engine.run_daily_recon(RECON_DATE)
        records = gov.list_records()
        assert len(records) == 1

    def test_draft_return_type_is_breach_report(self) -> None:
        from services.gabriel.breach_handler import InMemoryBreachRegistrar
        from services.gabriel.gabriel_models import (
            GabrielReturnType,
            InMemoryGabrielAuditPort,
        )
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        engine = self._shortfall_engine(gov, reg)
        engine.run_daily_recon(RECON_DATE)
        assert gov.list_records()[0].return_type == GabrielReturnType.BREACH_REPORT

    def test_draft_status_is_draft(self) -> None:
        from services.gabriel.breach_handler import InMemoryBreachRegistrar
        from services.gabriel.gabriel_models import (
            GabrielReturnStatus,
            InMemoryGabrielAuditPort,
        )
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        engine = self._shortfall_engine(gov, reg)
        engine.run_daily_recon(RECON_DATE)
        assert gov.list_records()[0].status == GabrielReturnStatus.DRAFT

    def test_draft_source_recon_id_set(self) -> None:
        from services.gabriel.breach_handler import InMemoryBreachRegistrar
        from services.gabriel.gabriel_models import InMemoryGabrielAuditPort
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        engine = self._shortfall_engine(gov, reg)
        engine.run_daily_recon(RECON_DATE)
        record = gov.list_records()[0]
        assert record.source_recon_id is not None
        assert len(record.source_recon_id) > 0

    def test_no_shortfall_no_draft(self) -> None:
        from services.gabriel.breach_handler import (
            GabrielBreachHandler,
            InMemoryBreachRegistrar,
        )
        from services.gabriel.gabriel_models import InMemoryGabrielAuditPort
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        handler = GabrielBreachHandler(governor=gov, registrar=reg)
        ledger = InMemoryLedgerPort()
        ledger.add_client_fund("CLIENT-001", Decimal("50000.00"))
        ledger.add_safeguarding("SAFEG-001", Decimal("50000.00"))  # balanced
        engine = ReconciliationEngine(ledger=ledger, breach_notifier=handler)
        engine.run_daily_recon(RECON_DATE)
        assert gov.list_records() == []

    def test_mlro_can_approve_draft(self) -> None:
        """Full HITL path: shortfall → DRAFT → MLRO approves → SUBMITTED (I-27)."""
        from services.gabriel.breach_handler import InMemoryBreachRegistrar
        from services.gabriel.gabriel_models import (
            GabrielReturnStatus,
            InMemoryGabrielAuditPort,
            InMemoryGabrielSubmissionPort,
        )
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        engine = self._shortfall_engine(gov, reg)
        engine.run_daily_recon(RECON_DATE)
        draft = gov.list_records()[0]
        sub_port = InMemoryGabrielSubmissionPort()
        submitted = gov.approve(draft.submission_id, "MLRO-TestUser", sub_port)
        assert submitted.status == GabrielReturnStatus.SUBMITTED
        assert len(sub_port.submitted) == 1

    def test_registrar_receives_breach_event(self) -> None:
        from services.gabriel.breach_handler import InMemoryBreachRegistrar
        from services.gabriel.gabriel_models import InMemoryGabrielAuditPort
        from services.gabriel.returns_governor import ReturnsGovernor

        gov = ReturnsGovernor(audit=InMemoryGabrielAuditPort())
        reg = InMemoryBreachRegistrar()
        engine = self._shortfall_engine(gov, reg)
        engine.run_daily_recon(RECON_DATE)
        assert len(reg.registered) == 1
        assert reg.registered[0].shortfall == Decimal("1000.00")
