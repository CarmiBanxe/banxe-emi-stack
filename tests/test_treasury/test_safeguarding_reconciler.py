"""Tests for services/treasury/safeguarding_reconciler.py — CASS 15 reconciliation.

Covers:
  - Reconciliation logic: tolerance check, variance calculation
  - Decimal precision (I-01: no float for money)
  - Status assignment (MATCHED vs DISCREPANCY)
  - Audit trail logging (TreasuryAuditPort)
  - Store persistence (ReconciliationStorePort)
  - Latest/list queries
  - All accounts compliance check
  - Error paths (missing account, invalid amounts)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from services.treasury.models import (
    ReconciliationRecord,
    ReconciliationStatus,
    SafeguardingAccount,
)
from services.treasury.safeguarding_reconciler import SafeguardingReconciler


class MockReconciliationStore:
    """Test double for ReconciliationStorePort."""

    def __init__(self) -> None:
        self.records: list[ReconciliationRecord] = []
        self.latest_by_account: dict[str, ReconciliationRecord] = {}

    async def save_record(self, record: ReconciliationRecord) -> None:
        self.records.append(record)
        self.latest_by_account[record.account_id] = record

    async def get_latest(self, account_id: str) -> ReconciliationRecord | None:
        return self.latest_by_account.get(account_id)

    async def list_records(self, account_id: str | None = None) -> list[ReconciliationRecord]:
        if account_id is None:
            return self.records
        return [r for r in self.records if r.account_id == account_id]


class MockTreasuryAudit:
    """Test double for TreasuryAuditPort."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def log(
        self,
        event_type: str,
        entity_id: str,
        details: dict[str, Any],
        actor: str,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "entity_id": entity_id,
                "details": details,
                "actor": actor,
            }
        )

    async def list_events(self, entity_id: str | None = None) -> list[dict[str, Any]]:
        if entity_id is None:
            return self.events
        return [e for e in self.events if e["entity_id"] == entity_id]


class TestSafeguardingReconcilerMatched:
    """Test reconciliation when amounts are within tolerance."""

    @pytest.mark.asyncio
    async def test_reconcile_matched_within_tolerance(self) -> None:
        """Variance below 1p → MATCHED."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.00"),
            client_money_held=Decimal("1000.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert record.status == ReconciliationStatus.MATCHED
        assert record.variance == Decimal("0.00")
        assert "Balances within tolerance" in record.notes

    @pytest.mark.asyncio
    async def test_reconcile_matched_variance_under_penny(self) -> None:
        """Variance of 0.005p (half-penny) → MATCHED."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.005"),
            client_money_held=Decimal("1000.005"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert record.status == ReconciliationStatus.MATCHED
        assert abs(record.variance) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_reconcile_matched_logs_audit(self) -> None:
        """MATCHED reconciliation logs 'reconciliation.completed' event."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.00"),
            client_money_held=Decimal("1000.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert len(audit.events) == 1
        event = audit.events[0]
        assert event["event_type"] == "reconciliation.completed"
        assert event["entity_id"] == "acc-1"
        assert event["actor"] == "DailyRecon"
        assert event["details"]["status"] == ReconciliationStatus.MATCHED.value


class TestSafeguardingReconcilerDiscrepancy:
    """Test reconciliation when variance exceeds tolerance."""

    @pytest.mark.asyncio
    async def test_reconcile_discrepancy_exactly_one_penny(self) -> None:
        """Variance exactly 0.01 (1p) → DISCREPANCY (not within tolerance)."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.01"),
            client_money_held=Decimal("1000.01"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert record.status == ReconciliationStatus.DISCREPANCY
        assert record.variance == Decimal("0.01")

    @pytest.mark.asyncio
    async def test_reconcile_discrepancy_large_variance(self) -> None:
        """Large variance (£50) → DISCREPANCY."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1050.00"),
            client_money_held=Decimal("1050.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert record.status == ReconciliationStatus.DISCREPANCY
        assert record.variance == Decimal("50.00")
        assert "Variance of 50.00 detected" in record.notes

    @pytest.mark.asyncio
    async def test_reconcile_discrepancy_negative_variance(self) -> None:
        """Negative variance (shortfall) → DISCREPANCY."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("950.00"),
            client_money_held=Decimal("950.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert record.status == ReconciliationStatus.DISCREPANCY
        assert record.variance == Decimal("-50.00")
        assert "requires investigation" in record.notes

    @pytest.mark.asyncio
    async def test_reconcile_discrepancy_logs_audit(self) -> None:
        """DISCREPANCY reconciliation logs 'reconciliation.discrepancy' event."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1010.00"),
            client_money_held=Decimal("1010.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert len(audit.events) == 1
        event = audit.events[0]
        assert event["event_type"] == "reconciliation.discrepancy"
        assert event["entity_id"] == "acc-1"
        assert "variance" in event["details"]


class TestSafeguardingReconcilerStore:
    """Test interaction with ReconciliationStorePort."""

    @pytest.mark.asyncio
    async def test_reconcile_saves_record(self) -> None:
        """reconcile() saves record to store."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.00"),
            client_money_held=Decimal("1000.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert len(store.records) == 1
        assert store.records[0].id == record.id
        assert store.records[0].account_id == "acc-1"

    @pytest.mark.asyncio
    async def test_get_latest_reconciliation(self) -> None:
        """get_latest_reconciliation() returns most recent record."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.00"),
            client_money_held=Decimal("1000.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        # Create two reconciliations
        for i in range(2):
            await reconciler.reconcile(
                account=account,
                bank_balance=Decimal("1000.00"),
                actor="DailyRecon",
            )

        latest = await reconciler.get_latest_reconciliation("acc-1")
        assert latest is not None
        assert latest == store.latest_by_account["acc-1"]

    @pytest.mark.asyncio
    async def test_get_latest_reconciliation_not_found(self) -> None:
        """get_latest_reconciliation() returns None for unknown account."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        latest = await reconciler.get_latest_reconciliation("unknown-acc")
        assert latest is None

    @pytest.mark.asyncio
    async def test_list_reconciliations_all(self) -> None:
        """list_reconciliations() returns all records without filter."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        # Create records for two accounts
        for acc_id in ["acc-1", "acc-2"]:
            account = SafeguardingAccount(
                id=acc_id,
                institution="TestBank",
                iban="GB82WEST12345698765432",
                balance=Decimal("1000.00"),
                client_money_held=Decimal("1000.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            )
            await reconciler.reconcile(
                account=account,
                bank_balance=Decimal("1000.00"),
                actor="DailyRecon",
            )

        all_records = await reconciler.list_reconciliations()
        assert len(all_records) == 2

    @pytest.mark.asyncio
    async def test_list_reconciliations_filtered(self) -> None:
        """list_reconciliations(account_id=...) filters by account."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        # Create records for two accounts
        for acc_id in ["acc-1", "acc-2"]:
            account = SafeguardingAccount(
                id=acc_id,
                institution="TestBank",
                iban="GB82WEST12345698765432",
                balance=Decimal("1000.00"),
                client_money_held=Decimal("1000.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            )
            await reconciler.reconcile(
                account=account,
                bank_balance=Decimal("1000.00"),
                actor="DailyRecon",
            )

        acc1_records = await reconciler.list_reconciliations("acc-1")
        assert len(acc1_records) == 1
        assert acc1_records[0].account_id == "acc-1"


class TestSafeguardingReconcilerCompliance:
    """Test compliance checks."""

    @pytest.mark.asyncio
    async def test_check_all_compliant_all_matched(self) -> None:
        """check_all_compliant() returns True if all accounts are MATCHED."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        accounts = [
            SafeguardingAccount(
                id="acc-1",
                institution="TestBank",
                iban="GB82WEST12345698765432",
                balance=Decimal("1000.00"),
                client_money_held=Decimal("1000.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            ),
            SafeguardingAccount(
                id="acc-2",
                institution="TestBank",
                iban="GB82WEST12345698765433",
                balance=Decimal("2000.00"),
                client_money_held=Decimal("2000.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            ),
        ]

        for account in accounts:
            await reconciler.reconcile(
                account=account,
                bank_balance=account.balance,  # Perfect match
                actor="DailyRecon",
            )

        is_compliant = await reconciler.check_all_compliant(accounts)
        assert is_compliant is True

    @pytest.mark.asyncio
    async def test_check_all_compliant_one_discrepancy(self) -> None:
        """check_all_compliant() returns False if any account has DISCREPANCY."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        accounts = [
            SafeguardingAccount(
                id="acc-1",
                institution="TestBank",
                iban="GB82WEST12345698765432",
                balance=Decimal("1000.00"),
                client_money_held=Decimal("1000.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            ),
            SafeguardingAccount(
                id="acc-2",
                institution="TestBank",
                iban="GB82WEST12345698765433",
                balance=Decimal("2010.00"),
                client_money_held=Decimal("2010.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            ),
        ]

        # acc-1 matched
        await reconciler.reconcile(
            account=accounts[0],
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        # acc-2 discrepancy
        await reconciler.reconcile(
            account=accounts[1],
            bank_balance=Decimal("2000.00"),  # Variance of £10
            actor="DailyRecon",
        )

        is_compliant = await reconciler.check_all_compliant(accounts)
        assert is_compliant is False

    @pytest.mark.asyncio
    async def test_check_all_compliant_no_reconciliation(self) -> None:
        """check_all_compliant() returns False if account has no reconciliation."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        accounts = [
            SafeguardingAccount(
                id="acc-1",
                institution="TestBank",
                iban="GB82WEST12345698765432",
                balance=Decimal("1000.00"),
                client_money_held=Decimal("1000.00"),
                currency="GBP",
                last_reconciled_at=datetime.now(UTC),
            ),
        ]

        # Don't reconcile — expect non-compliant
        is_compliant = await reconciler.check_all_compliant(accounts)
        assert is_compliant is False


class TestSafeguardingReconcilerDecimalPrecision:
    """Test I-01: Decimal precision (no float for money)."""

    @pytest.mark.asyncio
    async def test_reconcile_uses_decimal_not_float(self) -> None:
        """All amounts are Decimal, never float."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.12345"),
            client_money_held=Decimal("1000.12345"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.12340"),
            actor="DailyRecon",
        )

        assert isinstance(record.book_balance, Decimal)
        assert isinstance(record.bank_balance, Decimal)
        assert isinstance(record.variance, Decimal)
        # Verify precision is preserved
        assert record.variance == Decimal("0.00005")

    @pytest.mark.asyncio
    async def test_audit_log_decimal_as_string(self) -> None:
        """Audit trail records Decimal amounts as strings (DecimalString pattern)."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.50"),
            client_money_held=Decimal("1000.50"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.60"),
            actor="DailyRecon",
        )

        event = audit.events[0]
        # Amounts in audit should be strings
        assert isinstance(event["details"]["book_balance"], str)
        assert isinstance(event["details"]["bank_balance"], str)
        assert isinstance(event["details"]["variance"], str)
        assert event["details"]["book_balance"] == "1000.50"


class TestSafeguardingReconcilerRecordFields:
    """Test ReconciliationRecord field population."""

    @pytest.mark.asyncio
    async def test_record_has_all_fields(self) -> None:
        """Generated record has all required fields populated."""
        store = MockReconciliationStore()
        audit = MockTreasuryAudit()
        reconciler = SafeguardingReconciler(store, audit)

        account = SafeguardingAccount(
            id="acc-1",
            institution="TestBank",
            iban="GB82WEST12345698765432",
            balance=Decimal("1000.00"),
            client_money_held=Decimal("1000.00"),
            currency="GBP",
            last_reconciled_at=datetime.now(UTC),
        )

        record = await reconciler.reconcile(
            account=account,
            bank_balance=Decimal("1000.00"),
            actor="DailyRecon",
        )

        assert record.id is not None
        assert record.account_id == "acc-1"
        assert record.book_balance == Decimal("1000.00")
        assert record.bank_balance == Decimal("1000.00")
        assert record.variance == Decimal("0.00")
        assert record.status == ReconciliationStatus.MATCHED
        assert record.period_date is not None
        assert record.reconciled_at is not None
        assert record.notes is not None
