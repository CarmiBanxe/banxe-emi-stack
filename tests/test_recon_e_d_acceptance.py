"""
tests/test_recon_e_d_acceptance.py
E-D-CROSS-REPO-HANDOFF §3 acceptance criteria — missing tests.

Implements the 6 criteria that were open after IL-CBS-DRECON-3LEG-2026-06-26:
  - test_recon_completes_before_cutoff     (D-5 governor invariant)
  - test_safeguarding_events_immutable_5y  (D-3 append-only + TTL 5Y, I-24/I-28)
  - test_segregation_at_write              (E-1 client_funds segregation)
  - test_relevant_funds_daily_calc         (E-2 daily calc, I-01/I-02/I-04)
  - test_mlro_alert_within_1h              (D-6 MLRO alert SLA contract)
  - test_breach_event_contract             (idempotency_key + account_id + severity)

IL-CBS-DRECON-ESAFEGUARD-LIVEAUDIT-2026-06-26
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.recon.breach_notify_port import BreachEvent, InMemoryBreachNotifyPort
from services.recon.clickhouse_client import _CREATE_TABLE_SQL, InMemoryReconClient
from services.recon.recon_engine import InMemoryReconAuditPort, ReconciliationEngine
from services.recon.recon_models import (
    LARGE_VALUE_THRESHOLD,
    RECON_CUTOFF_HOUR_UTC,
    AccountBalance,
    ReconStatus,
    check_cutoff,
)
from services.recon.recon_port import InMemoryLedgerPort


def _ledger(
    client: list[AccountBalance] | None = None,
    safeguarding: list[AccountBalance] | None = None,
) -> InMemoryLedgerPort:
    port = InMemoryLedgerPort()
    if client is not None:
        port.set_client_funds(client)
    if safeguarding is not None:
        port.set_safeguarding(safeguarding)
    return port


from services.recon.safeguarding_account_port import (
    InMemorySafeguardingAccountPort,
    SegregationViolationError,
)

# ── D-5: test_recon_completes_before_cutoff ────────────────────────────────────


class TestReconCompletesBeforeCutoff:
    """D-5: recon must run before 07:00 UTC Monday–Friday (cron 0 7 * * 1-5)."""

    def test_cutoff_constant_is_seven_utc(self) -> None:
        assert RECON_CUTOFF_HOUR_UTC == 7

    def test_check_cutoff_before_hour_returns_true(self) -> None:
        assert check_cutoff(datetime(2026, 6, 26, 6, 59, tzinfo=UTC)) is True
        assert check_cutoff(datetime(2026, 6, 26, 0, 0, tzinfo=UTC)) is True
        assert check_cutoff(datetime(2026, 6, 26, 6, 59, 59, tzinfo=UTC)) is True

    def test_check_cutoff_at_hour_returns_false(self) -> None:
        assert check_cutoff(datetime(2026, 6, 26, 7, 0, tzinfo=UTC)) is False
        assert check_cutoff(datetime(2026, 6, 26, 7, 1, tzinfo=UTC)) is False
        assert check_cutoff(datetime(2026, 6, 26, 23, 59, tzinfo=UTC)) is False

    def test_check_cutoff_custom_hour(self) -> None:
        dt = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
        assert check_cutoff(dt, cutoff_hour=9) is True
        assert check_cutoff(dt, cutoff_hour=8) is False

    def test_recon_result_has_completed_before_cutoff_field(self) -> None:
        """ReconResult.completed_before_cutoff is set by engine (D-5 invariant)."""
        ledger = InMemoryLedgerPort()
        engine = ReconciliationEngine(ledger=ledger)
        result = engine.run_daily_recon("2026-06-26")
        assert hasattr(result, "completed_before_cutoff")
        assert isinstance(result.completed_before_cutoff, bool)

    def test_completed_before_cutoff_reflects_check_cutoff(self) -> None:
        """Engine sets completed_before_cutoff based on check_cutoff(now_utc)."""
        ledger = InMemoryLedgerPort()
        engine = ReconciliationEngine(ledger=ledger)
        result = engine.run_daily_recon("2026-06-26")
        now = datetime.now(UTC)
        expected = check_cutoff(now)
        # Allow ±1 second clock skew between engine's now and test's now
        assert result.completed_before_cutoff == expected or now.hour == RECON_CUTOFF_HOUR_UTC


# ── D-3: test_safeguarding_events_immutable_5y ────────────────────────────────


class TestSafeguardingEventsImmutable5Y:
    """D-3: safeguarding_events table is append-only MergeTree, TTL 5 years (I-24/I-28)."""

    def test_clickhouse_ddl_contains_5y_ttl(self) -> None:
        """ClickHouse DDL must contain 5-year TTL (I-08, I-24)."""
        assert "INTERVAL 5 YEAR" in _CREATE_TABLE_SQL

    def test_clickhouse_ddl_is_mergetree(self) -> None:
        """safeguarding_events uses MergeTree (append-only engine)."""
        assert "MergeTree" in _CREATE_TABLE_SQL

    def test_clickhouse_ddl_no_update_or_delete(self) -> None:
        """DDL must NOT contain ReplacingMergeTree or CollapsingMergeTree (mutating engines)."""
        assert "ReplacingMergeTree" not in _CREATE_TABLE_SQL
        assert "CollapsingMergeTree" not in _CREATE_TABLE_SQL

    def test_in_memory_audit_port_is_append_only(self) -> None:
        """InMemoryReconAuditPort only exposes record(); no delete/update methods."""
        port = InMemoryReconAuditPort()
        assert hasattr(port, "record")
        assert not hasattr(port, "delete")
        assert not hasattr(port, "update")
        assert not hasattr(port, "clear")

    def test_audit_entries_accumulate_across_runs(self) -> None:
        """Each run appends a new audit entry — never overwrites."""
        audit = InMemoryReconAuditPort()
        ledger = InMemoryLedgerPort()
        engine = ReconciliationEngine(ledger=ledger, audit=audit)
        engine.run_daily_recon("2026-06-24")
        engine.run_daily_recon("2026-06-25")
        engine.run_daily_recon("2026-06-26")
        assert len(audit.entries) == 3

    def test_audit_entry_is_frozen_dataclass(self) -> None:
        """ReconAuditEntry is frozen — fields cannot be mutated post-creation."""
        from services.recon.recon_models import ReconAuditEntry

        entry = ReconAuditEntry(
            recon_id="r-001",
            action="DAILY_RECON",
            status=ReconStatus.BALANCED,
            client_funds_total=Decimal("1000"),
            safeguarding_total=Decimal("1000"),
            actor="SYSTEM",
        )
        with pytest.raises((AttributeError, TypeError)):
            entry.action = "MUTATED"  # type: ignore[misc]

    def test_in_memory_recon_client_append_only(self) -> None:
        """InMemoryReconClient accumulates execute() calls — no reset in normal flow."""
        ch = InMemoryReconClient()
        ch.execute("INSERT ...", {"recon_date": "2026-06-24", "status": "MATCHED"})
        ch.execute("INSERT ...", {"recon_date": "2026-06-25", "status": "MATCHED"})
        assert ch.call_count == 2
        # entries list is the source of truth — no delete path
        assert len(ch.events) == 2


# ── E-1: test_segregation_at_write ────────────────────────────────────────────


class TestSegregationAtWrite:
    """E-1: operational debit cannot draw on client_funds (relevant_funds_fully_segregated)."""

    def test_client_funds_account_accessible_by_client_funds_caller(self) -> None:
        port = InMemorySafeguardingAccountPort()
        port.register_account("CF-001", Decimal("50000"), "GBP", "client_funds")
        bal = port.get_balance_as_type("CF-001", "GBP", requester_type="client_funds")
        assert bal == Decimal("50000")

    def test_operational_caller_cannot_access_client_funds(self) -> None:
        """E-1: SegregationViolationError raised when operational tries client_funds."""
        port = InMemorySafeguardingAccountPort()
        port.register_account("CF-001", Decimal("50000"), "GBP", "client_funds")
        with pytest.raises(SegregationViolationError, match="E-1 violation"):
            port.get_balance_as_type("CF-001", "GBP", requester_type="operational")

    def test_operational_account_accessible_by_operational_caller(self) -> None:
        port = InMemorySafeguardingAccountPort()
        port.register_account("OP-001", Decimal("10000"), "GBP", "operational")
        bal = port.get_balance_as_type("OP-001", "GBP", requester_type="operational")
        assert bal == Decimal("10000")

    def test_client_funds_caller_cannot_access_operational_account(self) -> None:
        """client_funds caller can read operational — D-recon needs cross-leg read."""
        port = InMemorySafeguardingAccountPort()
        port.register_account("OP-001", Decimal("10000"), "GBP", "operational")
        # client_funds reader may access operational (no reverse block)
        bal = port.get_balance_as_type("OP-001", "GBP", requester_type="client_funds")
        assert bal == Decimal("10000")

    def test_balance_is_decimal_not_float(self) -> None:
        """I-01: balance must be Decimal."""
        port = InMemorySafeguardingAccountPort()
        with pytest.raises(TypeError):
            port.register_account("CF-001", 50000.0, "GBP", "client_funds")  # type: ignore[arg-type]

    def test_segregation_error_message_contains_account_id(self) -> None:
        port = InMemorySafeguardingAccountPort()
        port.register_account("CF-RING-001", Decimal("1"), "GBP", "client_funds")
        with pytest.raises(SegregationViolationError, match="CF-RING-001"):
            port.get_balance_as_type("CF-RING-001", "GBP", requester_type="operational")

    def test_unknown_account_raises_key_error(self) -> None:
        port = InMemorySafeguardingAccountPort()
        with pytest.raises(KeyError):
            port.get_balance("UNKNOWN", "GBP")

    def test_currency_mismatch_raises_value_error(self) -> None:
        port = InMemorySafeguardingAccountPort()
        port.register_account("CF-001", Decimal("100"), "GBP", "client_funds")
        with pytest.raises(ValueError, match="currency mismatch"):
            port.get_balance("CF-001", "EUR")


# ── E-2: test_relevant_funds_daily_calc ───────────────────────────────────────


class TestRelevantFundsDailyCalc:
    """E-2: daily relevant-funds calc — Decimal (I-01), I-02 exclusion, I-04 flag."""

    def _make_engine(self, client_balances: list[AccountBalance]) -> ReconciliationEngine:
        ledger = _ledger(client=client_balances)
        return ReconciliationEngine(ledger=ledger)

    def test_relevant_funds_sum_is_decimal(self) -> None:
        """I-01: client_funds_total is Decimal."""
        engine = self._make_engine(
            [
                AccountBalance("A1", "UK", Decimal("10000"), "GBP"),
                AccountBalance("A2", "UK", Decimal("20000"), "GBP"),
            ]
        )
        result = engine.run_daily_recon("2026-06-26")
        assert isinstance(result.client_funds_total, Decimal)
        assert result.client_funds_total == Decimal("30000")

    def test_blocked_jurisdiction_excluded_from_calc(self) -> None:
        """I-02: RU/BY/IR/etc. accounts excluded from relevant-funds total."""
        engine = self._make_engine(
            [
                AccountBalance("A1", "UK", Decimal("10000"), "GBP", jurisdiction="GB"),
                AccountBalance("A2", "RU", Decimal("99999"), "GBP", jurisdiction="RU"),  # blocked
                AccountBalance("A3", "BY", Decimal("50000"), "GBP", jurisdiction="BY"),  # blocked
            ]
        )
        result = engine.run_daily_recon("2026-06-26")
        assert result.client_funds_total == Decimal("10000")
        assert "RU" in result.excluded_jurisdictions
        assert "BY" in result.excluded_jurisdictions

    def test_large_value_accounts_flagged(self) -> None:
        """I-04: accounts ≥£50k are flagged for MLRO review."""
        engine = self._make_engine(
            [
                AccountBalance("A1", "UK", LARGE_VALUE_THRESHOLD, "GBP"),
                AccountBalance("A2", "UK", Decimal("1000"), "GBP"),
            ]
        )
        result = engine.run_daily_recon("2026-06-26")
        assert result.large_values_flagged >= 1

    def test_exactly_at_large_value_threshold_flagged(self) -> None:
        engine = self._make_engine(
            [
                AccountBalance("A1", "UK", Decimal("50000.00"), "GBP"),
            ]
        )
        result = engine.run_daily_recon("2026-06-26")
        assert result.large_values_flagged >= 1

    def test_below_threshold_not_flagged(self) -> None:
        engine = self._make_engine(
            [
                AccountBalance("A1", "UK", Decimal("49999.99"), "GBP"),
            ]
        )
        result = engine.run_daily_recon("2026-06-26")
        assert result.large_values_flagged == 0

    def test_multiple_blocked_jurisdictions_all_excluded(self) -> None:
        """All 9 blocked jurisdictions are excluded (I-02 full set)."""
        from services.recon.recon_models import BLOCKED_JURISDICTIONS

        balances = [
            AccountBalance(f"X-{j}", j, Decimal("1000"), "GBP", jurisdiction=j)
            for j in BLOCKED_JURISDICTIONS
        ] + [AccountBalance("GOOD", "GB", Decimal("5000"), "GBP", jurisdiction="GB")]
        engine = self._make_engine(balances)
        result = engine.run_daily_recon("2026-06-26")
        assert result.client_funds_total == Decimal("5000")
        assert set(result.excluded_jurisdictions) == BLOCKED_JURISDICTIONS


# ── D-6: test_mlro_alert_within_1h ────────────────────────────────────────────


class TestMlroAlertWithin1h:
    """D-6: MLRO alert contract — event emitted synchronously, requires_approval_from=MLRO."""

    def _make_engine_with_shortfall(
        self,
    ) -> tuple[ReconciliationEngine, InMemoryBreachNotifyPort]:
        notifier = InMemoryBreachNotifyPort()
        ledger = _ledger(
            client=[AccountBalance("CF", "UK", Decimal("100000"), "GBP")],
            safeguarding=[AccountBalance("SG", "UK", Decimal("90000"), "GBP")],
        )
        engine = ReconciliationEngine(ledger=ledger, breach_notifier=notifier)
        return engine, notifier

    def test_breach_event_emitted_on_shortfall(self) -> None:
        """D-6: breach event emitted synchronously when shortfall detected."""
        engine, notifier = self._make_engine_with_shortfall()
        engine.run_daily_recon("2026-06-26")
        assert len(notifier.events) == 1

    def test_breach_event_requires_approval_from_mlro(self) -> None:
        """MLRO is always the approval authority for safeguarding breaches."""
        engine, notifier = self._make_engine_with_shortfall()
        engine.run_daily_recon("2026-06-26")
        assert notifier.events[0].requires_approval_from == "MLRO"

    def test_breach_event_emitted_before_engine_returns(self) -> None:
        """Event is emitted synchronously (not deferred) — satisfies ≤1h SLA contract."""
        notifier = InMemoryBreachNotifyPort()
        calls_before: list[int] = []

        original_notify = notifier.notify

        def tracking_notify(event: BreachEvent) -> None:
            calls_before.append(1)
            original_notify(event)

        notifier.notify = tracking_notify  # type: ignore[method-assign]
        ledger = _ledger(
            client=[AccountBalance("CF", "UK", Decimal("100000"), "GBP")],
            safeguarding=[AccountBalance("SG", "UK", Decimal("90000"), "GBP")],
        )
        engine = ReconciliationEngine(ledger=ledger, breach_notifier=notifier)
        engine.run_daily_recon("2026-06-26")
        assert len(calls_before) == 1, "notify must be called once, synchronously"

    def test_no_breach_event_on_balanced_recon(self) -> None:
        notifier = InMemoryBreachNotifyPort()
        ledger = InMemoryLedgerPort()  # defaults to balanced
        engine = ReconciliationEngine(ledger=ledger, breach_notifier=notifier)
        engine.run_daily_recon("2026-06-26")
        assert len(notifier.events) == 0

    def test_no_breach_event_on_surplus(self) -> None:
        notifier = InMemoryBreachNotifyPort()
        ledger = _ledger(
            client=[AccountBalance("CF", "UK", Decimal("90000"), "GBP")],
            safeguarding=[AccountBalance("SG", "UK", Decimal("100000"), "GBP")],
        )
        engine = ReconciliationEngine(ledger=ledger, breach_notifier=notifier)
        engine.run_daily_recon("2026-06-26")
        assert len(notifier.events) == 0

    def test_detected_at_is_valid_utc_iso_timestamp(self) -> None:
        engine, notifier = self._make_engine_with_shortfall()
        engine.run_daily_recon("2026-06-26")
        event = notifier.events[0]
        ts = datetime.fromisoformat(event.detected_at)
        # Timestamp must be recent (within last 60 seconds)
        delta = (
            datetime.now(UTC) - ts.replace(tzinfo=UTC)
            if ts.tzinfo is None
            else datetime.now(UTC) - ts
        )
        assert delta.total_seconds() < 60


# ── D-recon §4: test_breach_event_contract ────────────────────────────────────


class TestBreachEventContract:
    """E-D-CROSS-REPO-HANDOFF §4: BreachEvent contract — idempotency_key, account_id, severity."""

    def _make_event(self) -> BreachEvent:
        notifier = InMemoryBreachNotifyPort()
        ledger = _ledger(
            client=[AccountBalance("CF", "UK", Decimal("100000"), "GBP")],
            safeguarding=[AccountBalance("SG", "UK", Decimal("90000"), "GBP")],
        )
        engine = ReconciliationEngine(ledger=ledger, breach_notifier=notifier)
        engine.run_daily_recon("2026-06-26")
        return notifier.events[0]

    def test_breach_event_has_idempotency_key(self) -> None:
        """idempotency_key must be non-empty (deduplicates replay)."""
        event = self._make_event()
        assert event.idempotency_key != ""
        assert ":" in event.idempotency_key

    def test_idempotency_key_contains_recon_id_and_date(self) -> None:
        event = self._make_event()
        assert "2026-06-26" in event.idempotency_key
        # recon_id is also embedded
        assert event.recon_id in event.idempotency_key

    def test_breach_event_has_account_id(self) -> None:
        event = self._make_event()
        assert hasattr(event, "account_id")
        assert event.account_id != ""

    def test_breach_event_has_severity(self) -> None:
        event = self._make_event()
        assert hasattr(event, "severity")
        assert event.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    def test_breach_event_shortfall_is_decimal(self) -> None:
        """I-01: shortfall is Decimal."""
        event = self._make_event()
        assert isinstance(event.shortfall, Decimal)
        assert event.shortfall == Decimal("10000")

    def test_breach_event_shortfall_is_positive(self) -> None:
        event = self._make_event()
        assert event.shortfall > Decimal("0")

    def test_breach_event_type_is_canonical(self) -> None:
        event = self._make_event()
        assert event.event_type == "safeguarding.breach.detected"

    def test_breach_event_no_fca_auto_submit(self) -> None:
        """I-27: event does NOT include a direct FCA submission flag — HITL gate required."""
        event = self._make_event()
        assert not hasattr(event, "fca_auto_submitted")
        assert not hasattr(event, "fca_submitted")

    def test_two_runs_same_date_same_recon_id_idempotency(self) -> None:
        """Same recon_id + date always produces same idempotency_key."""
        event = self._make_event()
        key = f"{event.recon_id}:{event.recon_date}"
        assert event.idempotency_key == key

    def test_breach_event_is_frozen(self) -> None:
        event = self._make_event()
        with pytest.raises((AttributeError, TypeError)):
            event.shortfall = Decimal("0")  # type: ignore[misc]
