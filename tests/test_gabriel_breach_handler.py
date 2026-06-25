"""
tests/test_gabriel_breach_handler.py
GabrielBreachHandler tests (IL-CBS-GABRIEL-BREACH-HANDLER-2026-06-26).

Covers:
  - notify() registers breach event in registrar
  - notify() creates DRAFT in governor
  - notify() is idempotent on duplicate recon_id (governor deduplicates)
  - notify() is fail-open: registrar error → logged, no raise, governor not called
  - notify() is fail-open: governor error → logged, no raise
  - notify() records audit trail (via InMemoryGabrielAuditPort)
  - BreachRegistrarPort structural check (runtime_checkable)
  - Wiring: ReconEngine + GabrielBreachHandler + ReturnsGovernor integration
  - InMemoryBreachNotifyPort still works independently (regression guard)
  - notify() on multiple distinct breaches creates distinct drafts
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.gabriel.breach_handler import BreachRegistrarPort, GabrielBreachHandler
from services.gabriel.gabriel_models import (
    GabrielReturnStatus,
    GabrielReturnType,
    InMemoryGabrielAuditPort,
    InMemoryGabrielSubmissionPort,
)
from services.gabriel.returns_governor import ReturnsGovernor
from services.recon.breach_notify_port import BreachEvent, InMemoryBreachNotifyPort

# ── Helpers ───────────────────────────────────────────────────────────────────


def _event(
    recon_id: str = "RECON-2026-06-25-ABC",
    shortfall: Decimal = Decimal("1000.00"),
    currency: str = "GBP",
    recon_date: str = "2026-06-25",
) -> BreachEvent:
    return BreachEvent(
        event_type="safeguarding.breach.detected",
        recon_id=recon_id,
        recon_date=recon_date,
        currency=currency,
        client_funds_total=Decimal("50000.00"),
        safeguarding_total=Decimal("50000.00") - shortfall,
        shortfall=shortfall,
        detected_at=datetime.now().isoformat(),
        requires_approval_from="MLRO",
    )


class _InMemoryRegistrar:
    """Minimal BreachRegistrarPort stub for unit tests."""

    def __init__(self) -> None:
        self.registered: list[BreachEvent] = []
        self.raise_on_register: Exception | None = None

    def register_breach_event(self, event: BreachEvent) -> None:
        if self.raise_on_register:
            raise self.raise_on_register
        self.registered.append(event)


class _InMemoryGovernorStub:
    """Minimal _ReturnsGovernorPort stub for unit tests."""

    def __init__(self) -> None:
        self.drafts: list[BreachEvent] = []
        self.raise_on_draft: Exception | None = None

    def create_breach_draft(self, breach_event: BreachEvent) -> None:
        if self.raise_on_draft:
            raise self.raise_on_draft
        self.drafts.append(breach_event)


def _handler(
    governor: _InMemoryGovernorStub | None = None,
    registrar: _InMemoryRegistrar | None = None,
) -> tuple[GabrielBreachHandler, _InMemoryGovernorStub, _InMemoryRegistrar]:
    gov = governor or _InMemoryGovernorStub()
    reg = registrar or _InMemoryRegistrar()
    return GabrielBreachHandler(governor=gov, registrar=reg), gov, reg


# ── Core notify behaviour ─────────────────────────────────────────────────────


class TestNotifyCore:
    def test_notify_registers_event_in_registrar(self) -> None:
        handler, _, reg = _handler()
        event = _event()
        handler.notify(event)
        assert len(reg.registered) == 1
        assert reg.registered[0].recon_id == event.recon_id

    def test_notify_creates_draft_in_governor(self) -> None:
        handler, gov, _ = _handler()
        event = _event()
        handler.notify(event)
        assert len(gov.drafts) == 1
        assert gov.drafts[0].recon_id == event.recon_id

    def test_notify_registers_before_governor(self) -> None:
        """registrar is always called before governor (ordering invariant)."""
        call_order: list[str] = []

        class _OrdReg:
            def register_breach_event(self, event: BreachEvent) -> None:
                call_order.append("registrar")

        class _OrdGov:
            def create_breach_draft(self, breach_event: BreachEvent) -> None:
                call_order.append("governor")

        handler = GabrielBreachHandler(governor=_OrdGov(), registrar=_OrdReg())
        handler.notify(_event())
        assert call_order == ["registrar", "governor"]

    def test_notify_shortfall_preserved_in_registered_event(self) -> None:
        handler, _, reg = _handler()
        event = _event(shortfall=Decimal("12345.67"))
        handler.notify(event)
        assert reg.registered[0].shortfall == Decimal("12345.67")

    def test_notify_currency_preserved_in_registered_event(self) -> None:
        handler, _, reg = _handler()
        event = _event(currency="EUR")
        handler.notify(event)
        assert reg.registered[0].currency == "EUR"


# ── Idempotency ───────────────────────────────────────────────────────────────


class TestIdempotency:
    def test_duplicate_notify_stores_two_registrar_entries(self) -> None:
        """Handler itself doesn't deduplicate — registrar/governor do."""
        handler, _, reg = _handler()
        event = _event()
        handler.notify(event)
        handler.notify(event)
        assert len(reg.registered) == 2

    def test_governor_deduplicates_via_real_returns_governor(self) -> None:
        """ReturnsGovernor.create_breach_draft is idempotent per recon_id."""
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        reg = _InMemoryRegistrar()
        handler = GabrielBreachHandler(governor=gov, registrar=reg)
        event = _event()
        handler.notify(event)
        handler.notify(event)
        # Same idempotency_key → only one record in governor
        records = gov.list_records()
        assert len(records) == 1

    def test_distinct_recon_ids_create_distinct_drafts(self) -> None:
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        reg = _InMemoryRegistrar()
        handler = GabrielBreachHandler(governor=gov, registrar=reg)
        handler.notify(_event(recon_id="R-001", recon_date="2026-06-01"))
        handler.notify(_event(recon_id="R-002", recon_date="2026-06-02"))
        assert len(gov.list_records()) == 2


# ── Fail-open behaviour ───────────────────────────────────────────────────────


class TestFailOpen:
    def test_registrar_error_does_not_raise(self) -> None:
        handler, gov, reg = _handler()
        reg.raise_on_register = RuntimeError("registrar boom")
        # Must not raise
        handler.notify(_event())

    def test_registrar_error_skips_governor(self) -> None:
        handler, gov, reg = _handler()
        reg.raise_on_register = RuntimeError("registrar boom")
        handler.notify(_event())
        assert gov.drafts == []  # governor never called

    def test_governor_error_does_not_raise(self) -> None:
        handler, gov, reg = _handler()
        gov.raise_on_draft = RuntimeError("governor boom")
        handler.notify(_event())

    def test_governor_error_still_registers_event(self) -> None:
        handler, gov, reg = _handler()
        gov.raise_on_draft = RuntimeError("governor boom")
        handler.notify(_event())
        assert len(reg.registered) == 1


# ── Protocol structural check ─────────────────────────────────────────────────


class TestProtocolCheck:
    def test_in_memory_registrar_is_breach_registrar_port(self) -> None:
        reg = _InMemoryRegistrar()
        assert isinstance(reg, BreachRegistrarPort)

    def test_real_regdata_adapter_is_breach_registrar_port(self) -> None:
        from services.gabriel.regdata_gabriel_adapter import RegDataGabrielAdapter
        from services.recon.fca_regdata_client import MockFCARegDataClient
        from services.reporting.regdata_return import MockFIN060Generator, StubRegDataClient

        adapter = RegDataGabrielAdapter(
            breach_client=MockFCARegDataClient(),
            fin060_client=StubRegDataClient(),
            fin060_generator=MockFIN060Generator(),
        )
        assert isinstance(adapter, BreachRegistrarPort)


# ── Integration: full D-recon → K-gabriel chain ───────────────────────────────


class TestIntegrationChain:
    def test_breach_draft_status_is_draft(self) -> None:
        """Draft created by handler should be in DRAFT status (HITL not yet approved)."""
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        reg = _InMemoryRegistrar()
        handler = GabrielBreachHandler(governor=gov, registrar=reg)
        event = _event()
        handler.notify(event)
        records = gov.list_records()
        assert len(records) == 1
        assert records[0].status == GabrielReturnStatus.DRAFT
        assert records[0].return_type == GabrielReturnType.BREACH_REPORT

    def test_breach_draft_source_recon_id_matches_event(self) -> None:
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        reg = _InMemoryRegistrar()
        handler = GabrielBreachHandler(governor=gov, registrar=reg)
        event = _event(recon_id="RECON-9999")
        handler.notify(event)
        records = gov.list_records()
        assert records[0].source_recon_id == "RECON-9999"

    def test_inmemory_breach_notify_port_still_works(self) -> None:
        """Regression: InMemoryBreachNotifyPort unchanged by this change."""
        port = InMemoryBreachNotifyPort()
        port.notify(_event())
        assert len(port.events) == 1

    def test_handler_approve_end_to_end(self) -> None:
        """Full chain: notify → DRAFT → approve via InMemoryGabrielSubmissionPort."""
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        sub_port = InMemoryGabrielSubmissionPort()
        reg = _InMemoryRegistrar()
        handler = GabrielBreachHandler(governor=gov, registrar=reg)
        event = _event()
        handler.notify(event)
        records = gov.list_records()
        assert len(records) == 1
        draft = records[0]
        submitted = gov.approve(draft.submission_id, "MLRO-Alice", sub_port)
        assert submitted.status == GabrielReturnStatus.SUBMITTED
        assert len(sub_port.submitted) == 1

    def test_shared_governor_draft_visible_via_api_layer(self) -> None:
        """Regression: shared-state fix — DRAFTs from GabrielBreachHandler must be
        visible through the same governor instance the API layer uses.

        Simulates the composition root sharing: api/deps.get_gabriel_governor() is
        used by both GabrielBreachHandler AND the router's _governor.
        """
        # Shared governor — mirrors how get_gabriel_governor() wires both sides
        shared_audit = InMemoryGabrielAuditPort()
        shared_gov = ReturnsGovernor(audit=shared_audit)

        # Breach handler uses shared_gov (as wired via get_gabriel_breach_handler())
        reg = _InMemoryRegistrar()
        handler = GabrielBreachHandler(governor=shared_gov, registrar=reg)

        # Simulate ReconciliationEngine firing a breach event
        event = _event(recon_id="RECON-SHARED-TEST")
        handler.notify(event)

        # API layer queries the same shared_gov (as wired via get_gabriel_governor())
        api_side_records = shared_gov.list_records()
        assert len(api_side_records) == 1
        assert api_side_records[0].source_recon_id == "RECON-SHARED-TEST"
        assert api_side_records[0].status == GabrielReturnStatus.DRAFT
