"""
services/fee_management/fee_agent.py
IL-FME-01 | Phase 41 | banxe-emi-stack

FeeAgent — orchestrates fee operations with HITL gates.
I-27: Waivers, refunds, schedule changes ALWAYS require human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.fee_management.models import (
    FeeCharge,
    FeeStatus,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
    WaiverReason,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class FeeAgent:
    """Autonomous fee processing agent with HITL gates for sensitive actions."""

    def __init__(
        self,
        rule_store: InMemoryFeeRuleStore | None = None,
        charge_store: InMemoryFeeChargeStore | None = None,
    ) -> None:
        self._rules = rule_store or InMemoryFeeRuleStore()
        self._charges = charge_store or InMemoryFeeChargeStore()

    def process_charge(self, account_id: str, rule_id: str, reference: str) -> dict:
        """Auto-apply charge (L1); return charge summary."""
        rule = self._rules.get_rule(rule_id)
        if rule is None:
            return {"error": f"Rule not found: {rule_id}"}
        charge = FeeCharge(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
            account_id=account_id,
            amount=rule.amount,
            status=FeeStatus.PENDING,
            description=rule.name,
            reference=reference,
            applied_at=datetime.now(UTC),
            paid_at=None,
        )
        self._charges.save_charge(charge)
        return {
            "charge_id": charge.id,
            "account_id": account_id,
            "amount": str(charge.amount),
            "status": charge.status.value,
            "autonomy_level": "L1",
        }

    def process_waiver_request(
        self,
        charge_id: str,
        account_id: str,
        reason: WaiverReason,
        requested_by: str,
    ) -> HITLProposal:
        """Fee waivers always require HITL (I-27)."""
        return HITLProposal(
            action="approve_waiver",
            resource_id=charge_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"Waiver for charge {charge_id} requested by {requested_by} "
                f"(reason={reason.value}) requires human approval (I-27)."
            ),
            autonomy_level="L4",
        )

    def process_refund(self, charge_id: str, amount: Decimal, reason: str) -> HITLProposal:
        """Refunds always require HITL (I-27)."""
        return HITLProposal(
            action="process_refund",
            resource_id=charge_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"Refund of £{amount} for charge {charge_id} "
                f"(reason={reason}) requires human approval (I-27)."
            ),
            autonomy_level="L4",
        )

    def process_schedule_change(self, schedule_id: str, changes: dict) -> HITLProposal:
        """Schedule changes always require HITL (I-27)."""
        return HITLProposal(
            action="update_fee_schedule",
            resource_id=schedule_id,
            requires_approval_from="CFO",
            reason=(
                f"Fee schedule change for {schedule_id} requires CFO approval "
                "per I-27 — AI proposes, human decides."
            ),
            autonomy_level="L4",
        )

    def get_agent_status(self) -> dict:
        """Return agent operational status."""
        rules = self._rules.list_rules(active_only=True)
        return {
            "agent": "FeeAgent",
            "status": "ACTIVE",
            "autonomy_level": "L1",
            "hitl_gates": ["waiver", "refund", "schedule_change"],
            "active_rules": len(rules),
            "timestamp": datetime.now(UTC).isoformat(),
        }
