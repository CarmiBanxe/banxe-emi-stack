"""
services/fee_management/billing_engine.py
IL-FME-01 | Phase 41 | banxe-emi-stack

BillingEngine — invoice generation, charge application, and billing history.
I-01: All monetary values as Decimal — NEVER float.
I-24: All billing/charge actions append to audit log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.fee_management.models import (
    BillingCycle,
    FeeCharge,
    FeeStatus,
    FeeSummary,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
)


class _AuditStub:
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        pass  # InMemory stub; replaced in production by AuditPort


class BillingEngine:
    """Generates invoices, applies charges, and manages billing lifecycle."""

    def __init__(
        self,
        rule_store: InMemoryFeeRuleStore | None = None,
        charge_store: InMemoryFeeChargeStore | None = None,
        audit_port: _AuditStub | None = None,
    ) -> None:
        self._rules = rule_store or InMemoryFeeRuleStore()
        self._charges = charge_store or InMemoryFeeChargeStore()
        self._audit = audit_port or _AuditStub()

    def generate_invoice(
        self,
        account_id: str,
        cycle: BillingCycle,
        period_start: datetime,
        period_end: datetime,
    ) -> FeeSummary:
        """Collect charges for period, compute totals, append to audit (I-24)."""
        charges = self._charges.list_charges(account_id)
        period_charges = [c for c in charges if period_start <= c.applied_at <= period_end]
        total_charged = sum((c.amount for c in period_charges), Decimal("0"))
        total_waived = sum(
            (c.amount for c in period_charges if c.status == FeeStatus.WAIVED),
            Decimal("0"),
        )
        total_paid = sum(
            (c.amount for c in period_charges if c.status == FeeStatus.APPLIED),
            Decimal("0"),
        )
        outstanding = sum(
            (c.amount for c in period_charges if c.status == FeeStatus.PENDING),
            Decimal("0"),
        )
        breakdown: dict[str, Decimal] = {}
        for charge in period_charges:
            rule = self._rules.get_rule(charge.rule_id)
            key = rule.category.value if rule else "OTHER"
            breakdown[key] = (breakdown.get(key, Decimal("0")) + charge.amount).quantize(
                Decimal("0.01")
            )
        summary = FeeSummary(
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            total_charged=total_charged.quantize(Decimal("0.01")),
            total_waived=total_waived.quantize(Decimal("0.01")),
            total_paid=total_paid.quantize(Decimal("0.01")),
            outstanding=outstanding.quantize(Decimal("0.01")),
            breakdown=breakdown,
        )
        self._audit.log(
            action="generate_invoice",
            resource_id=account_id,
            details={
                "cycle": cycle.value,
                "period_start": str(period_start),
                "period_end": str(period_end),
            },
            outcome="INVOICED",
        )
        return summary

    def apply_charges(
        self,
        account_id: str,
        rule_ids: list[str],
        reference: str,
    ) -> list[FeeCharge]:
        """Create FeeCharge for each rule; status=PENDING; logs to audit (I-24)."""
        now = datetime.now(UTC)
        created: list[FeeCharge] = []
        for rule_id in rule_ids:
            rule = self._rules.get_rule(rule_id)
            if rule is None:
                continue
            charge = FeeCharge(
                id=str(uuid.uuid4()),
                rule_id=rule_id,
                account_id=account_id,
                amount=rule.amount,
                status=FeeStatus.PENDING,
                description=rule.name,
                reference=reference,
                applied_at=now,
                paid_at=None,
            )
            self._charges.save_charge(charge)
            created.append(charge)
            self._audit.log(
                action="apply_charge",
                resource_id=charge.id,
                details={"account_id": account_id, "rule_id": rule_id, "amount": str(rule.amount)},
                outcome="PENDING",
            )
        return created

    def get_outstanding(self, account_id: str) -> list[FeeCharge]:
        """Return PENDING charges only."""
        charges = self._charges.list_charges(account_id)
        return [c for c in charges if c.status == FeeStatus.PENDING]

    def mark_paid(self, charge_id: str) -> FeeCharge:
        """Set status=APPLIED, paid_at=now; logs to audit (I-24)."""
        charge = self._charges.get_charge(charge_id)
        if charge is None:
            raise ValueError(f"Charge not found: {charge_id}")
        updated = FeeCharge(
            id=charge.id,
            rule_id=charge.rule_id,
            account_id=charge.account_id,
            amount=charge.amount,
            status=FeeStatus.APPLIED,
            description=charge.description,
            reference=charge.reference,
            applied_at=charge.applied_at,
            paid_at=datetime.now(UTC),
        )
        self._charges.save_charge(updated)
        self._audit.log(
            action="mark_paid",
            resource_id=charge_id,
            details={"account_id": charge.account_id, "amount": str(charge.amount)},
            outcome="APPLIED",
        )
        return updated

    def get_billing_history(self, account_id: str, limit: int = 50) -> list[FeeCharge]:
        """Return most recent N charges."""
        charges = self._charges.list_charges(account_id)
        return sorted(charges, key=lambda c: c.applied_at, reverse=True)[:limit]
