"""
services/fee_management/waiver_manager.py
IL-FME-01 | Phase 41 | banxe-emi-stack

WaiverManager — fee waiver lifecycle with mandatory HITL approval.
I-27: Fee waivers ALWAYS require human approval — AI proposes, human decides.
I-24: All waiver actions append to audit log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.fee_management.models import (
    FeeCharge,
    FeeStatus,
    FeeWaiver,
    InMemoryFeeChargeStore,
    InMemoryFeeWaiverStore,
    WaiverReason,
)


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


class WaiverManager:
    """Manages fee waiver requests with mandatory HITL gates (I-27)."""

    def __init__(
        self,
        charge_store: InMemoryFeeChargeStore | None = None,
        waiver_store: InMemoryFeeWaiverStore | None = None,
        audit_port: _AuditStub | None = None,
    ) -> None:
        self._charges = charge_store or InMemoryFeeChargeStore()
        self._waivers = waiver_store or InMemoryFeeWaiverStore()
        self._audit = audit_port or _AuditStub()

    def request_waiver(
        self,
        charge_id: str,
        account_id: str,
        reason: WaiverReason,
        requested_by: str,
    ) -> HITLProposal:
        """Fee waivers always require human approval (I-27)."""
        waiver = FeeWaiver(
            id=str(uuid.uuid4()),
            charge_id=charge_id,
            account_id=account_id,
            reason=reason,
            amount_waived=Decimal("0"),
            requested_by=requested_by,
            status="PENDING",
            created_at=datetime.now(UTC),
        )
        self._waivers.save_waiver(waiver)
        return HITLProposal(
            action="approve_waiver",
            resource_id=waiver.id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"Fee waiver request for charge {charge_id} (reason={reason.value}) "
                "requires human approval per I-27 — AI proposes, human decides."
            ),
            autonomy_level="L4",
        )

    def approve_waiver(self, waiver_id: str, approved_by: str) -> FeeWaiver:
        """Approve waiver; mark charge as WAIVED; append audit (I-24)."""
        waiver = self._waivers.get_waiver(waiver_id)
        if waiver is None:
            raise ValueError(f"Waiver not found: {waiver_id}")
        charge = self._charges.get_charge(waiver.charge_id)
        charge_amount = charge.amount if charge else Decimal("0")
        updated_waiver = FeeWaiver(
            id=waiver.id,
            charge_id=waiver.charge_id,
            account_id=waiver.account_id,
            reason=waiver.reason,
            amount_waived=charge_amount,
            requested_by=waiver.requested_by,
            approved_by=approved_by,
            status="APPROVED",
            created_at=waiver.created_at,
            resolved_at=datetime.now(UTC),
        )
        self._waivers.save_waiver(updated_waiver)
        if charge is not None:
            waived_charge = FeeCharge(
                id=charge.id,
                rule_id=charge.rule_id,
                account_id=charge.account_id,
                amount=charge.amount,
                status=FeeStatus.WAIVED,
                description=charge.description,
                reference=charge.reference,
                applied_at=charge.applied_at,
                paid_at=charge.paid_at,
            )
            self._charges.save_charge(waived_charge)
        self._audit.log(
            action="approve_waiver",
            resource_id=waiver_id,
            details={"approved_by": approved_by, "account_id": waiver.account_id},
            outcome="APPROVED",
        )
        return updated_waiver

    def reject_waiver(self, waiver_id: str, approved_by: str) -> FeeWaiver:
        """Reject waiver; append audit (I-24)."""
        waiver = self._waivers.get_waiver(waiver_id)
        if waiver is None:
            raise ValueError(f"Waiver not found: {waiver_id}")
        updated_waiver = FeeWaiver(
            id=waiver.id,
            charge_id=waiver.charge_id,
            account_id=waiver.account_id,
            reason=waiver.reason,
            amount_waived=Decimal("0"),
            requested_by=waiver.requested_by,
            approved_by=approved_by,
            status="REJECTED",
            created_at=waiver.created_at,
            resolved_at=datetime.now(UTC),
        )
        self._waivers.save_waiver(updated_waiver)
        self._audit.log(
            action="reject_waiver",
            resource_id=waiver_id,
            details={"approved_by": approved_by, "account_id": waiver.account_id},
            outcome="REJECTED",
        )
        return updated_waiver

    def list_active_waivers(self, account_id: str) -> list[FeeWaiver]:
        """Return PENDING + APPROVED waivers."""
        waivers = self._waivers.list_waivers(account_id)
        return [w for w in waivers if w.status in ("PENDING", "APPROVED")]

    def check_waiver_eligibility(self, account_id: str, reason: WaiverReason) -> dict:
        """Check eligibility for a waiver type."""
        if reason == WaiverReason.GOODWILL:
            return {
                "eligible": True,
                "reason": "GOODWILL waivers always eligible",
                "max_waiver": Decimal("50.00"),
            }
        if reason == WaiverReason.PROMOTION:
            ninety_days_ago = datetime.now(UTC) - timedelta(days=90)
            recent_promos = [
                w
                for w in self._waivers.list_waivers(account_id)
                if w.reason == WaiverReason.PROMOTION and w.created_at >= ninety_days_ago
            ]
            if len(recent_promos) < 3:
                return {
                    "eligible": True,
                    "reason": "Fewer than 3 promotional waivers in 90 days",
                    "max_waiver": Decimal("25.00"),
                }
            return {
                "eligible": False,
                "reason": "Exceeded 3 promotional waivers in last 90 days",
                "max_waiver": Decimal("0"),
            }
        return {
            "eligible": True,
            "reason": f"{reason.value} waiver eligible by default",
            "max_waiver": Decimal("100.00"),
        }
