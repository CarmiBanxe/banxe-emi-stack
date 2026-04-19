"""
services/fee_management/fee_reconciler.py
IL-FME-01 | Phase 41 | banxe-emi-stack

FeeReconciler — reconcile expected vs actual charges, flag overcharges.
I-01: All monetary values as Decimal — NEVER float.
I-27: Refunds always require human approval — HITL gated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from services.fee_management.models import (
    FeeCharge,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
)

OVERCHARGE_TOLERANCE = Decimal("0.01")


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class _AuditStub:
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        pass


class FeeReconciler:
    """Reconciles actual charges against expected fee rules."""

    def __init__(
        self,
        rule_store: InMemoryFeeRuleStore | None = None,
        charge_store: InMemoryFeeChargeStore | None = None,
        audit_port: _AuditStub | None = None,
    ) -> None:
        self._rules = rule_store or InMemoryFeeRuleStore()
        self._charges = charge_store or InMemoryFeeChargeStore()
        self._audit = audit_port or _AuditStub()

    def reconcile_charges(
        self,
        account_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        """Compare expected vs actual charges for period."""
        charges = self._charges.list_charges(account_id)
        period_charges = [c for c in charges if period_start <= c.applied_at <= period_end]
        matched = 0
        overcharged = 0
        undercharged = 0
        discrepancy = Decimal("0")
        for charge in period_charges:
            rule = self._rules.get_rule(charge.rule_id)
            if rule is None:
                continue
            expected = rule.amount
            diff = charge.amount - expected
            if abs(diff) <= OVERCHARGE_TOLERANCE:
                matched += 1
            elif diff > OVERCHARGE_TOLERANCE:
                overcharged += 1
                discrepancy += diff
            else:
                undercharged += 1
                discrepancy += diff
        return {
            "matched": matched,
            "overcharged": overcharged,
            "undercharged": undercharged,
            "discrepancy": discrepancy.quantize(Decimal("0.01")),
        }

    def flag_overcharges(
        self,
        account_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> list[FeeCharge]:
        """Return charges where amount > rule.amount + OVERCHARGE_TOLERANCE."""
        charges = self._charges.list_charges(account_id)
        period_charges = [c for c in charges if period_start <= c.applied_at <= period_end]
        overcharges = []
        for charge in period_charges:
            rule = self._rules.get_rule(charge.rule_id)
            if rule is None:
                continue
            if charge.amount > rule.amount + OVERCHARGE_TOLERANCE:
                overcharges.append(charge)
        return overcharges

    def generate_refund_proposal(
        self, charge_id: str, amount: Decimal, reason: str
    ) -> HITLProposal:
        """Refunds always require human approval (I-27)."""
        return HITLProposal(
            action="process_refund",
            resource_id=charge_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"Refund of {amount} for charge {charge_id} (reason={reason}) "
                "requires human approval per I-27 — AI proposes, human decides."
            ),
            autonomy_level="L4",
        )

    def get_reconciliation_report(self, account_id: str) -> dict:
        """Generate full reconciliation report for account."""
        charges = self._charges.list_charges(account_id)
        total_charges = sum((c.amount for c in charges), Decimal("0"))
        total_expected = Decimal("0")
        for charge in charges:
            rule = self._rules.get_rule(charge.rule_id)
            if rule:
                total_expected += rule.amount
        discrepancy = (total_charges - total_expected).quantize(Decimal("0.01"))
        status = "CLEAN" if abs(discrepancy) <= OVERCHARGE_TOLERANCE else "DISCREPANCY"
        return {
            "account_id": account_id,
            "total_charges": total_charges.quantize(Decimal("0.01")),
            "total_expected": total_expected.quantize(Decimal("0.01")),
            "discrepancy": discrepancy,
            "status": status,
        }
