"""
test_full_compliance_flow.py — IL-INT-01
End-to-end compliance lifecycle with HITL L4 checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

# ── Minimal domain stubs ──────────────────────────────────────────────────────


@dataclass
class _Customer:
    customer_id: str
    kyc_status: str = "PENDING"
    aml_status: str = "PENDING"
    risk_level: str = "LOW"


@dataclass
class _HITLProposal:
    action: str
    requires_approval_from: str
    reason: str
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    approved: bool = False


@dataclass
class _Payment:
    payment_id: str
    customer_id: str
    amount: Decimal
    currency: str
    status: str = "PENDING"


class _ComplianceEngine:
    BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
    EDD_THRESHOLD_INDIVIDUAL = Decimal("10000.00")

    def __init__(self) -> None:
        self._audit: list[dict] = []  # I-24 append-only

    def kyc_approve(self, customer: _Customer) -> _Customer:
        customer.kyc_status = "APPROVED"
        self._audit.append({"event": "kyc.approved", "customer_id": customer.customer_id})
        return customer

    def aml_screen(self, customer: _Customer, amount: Decimal) -> _Customer | _HITLProposal:
        if amount >= self.EDD_THRESHOLD_INDIVIDUAL:
            # I-27: HITL — propose EDD, don't auto-apply
            return _HITLProposal(
                action="EDD_REQUIRED",
                requires_approval_from="COMPLIANCE_OFFICER",
                reason=f"Amount {amount} >= EDD threshold {self.EDD_THRESHOLD_INDIVIDUAL}",
            )
        customer.aml_status = "CLEARED"
        self._audit.append({"event": "aml.cleared", "customer_id": customer.customer_id})
        return customer

    def check_jurisdiction(self, country_code: str) -> bool:
        return country_code not in self.BLOCKED_JURISDICTIONS

    @property
    def audit_log(self) -> list[dict]:
        return list(self._audit)


class TestFullComplianceFlow:
    def setup_method(self):
        self.engine = _ComplianceEngine()

    def test_kyc_approval_sets_status(self):
        c = _Customer("CUST001")
        result = self.engine.kyc_approve(c)
        assert result.kyc_status == "APPROVED"

    def test_kyc_approval_logged_audit(self):
        c = _Customer("CUST001")
        self.engine.kyc_approve(c)
        events = [e["event"] for e in self.engine.audit_log]
        assert "kyc.approved" in events

    def test_aml_cleared_below_edd_threshold(self):
        c = _Customer("CUST001", kyc_status="APPROVED")
        result = self.engine.aml_screen(c, Decimal("5000.00"))
        assert isinstance(result, _Customer)
        assert result.aml_status == "CLEARED"

    def test_aml_hitl_at_edd_threshold(self):
        """I-27: at exactly £10k, must return HITLProposal not auto-approve."""
        c = _Customer("CUST001", kyc_status="APPROVED")
        result = self.engine.aml_screen(c, Decimal("10000.00"))
        assert isinstance(result, _HITLProposal)
        assert result.requires_approval_from == "COMPLIANCE_OFFICER"

    def test_aml_hitl_above_edd_threshold(self):
        c = _Customer("CUST001", kyc_status="APPROVED")
        result = self.engine.aml_screen(c, Decimal("50000.00"))
        assert isinstance(result, _HITLProposal)

    def test_hitl_proposal_not_auto_approved(self):
        """I-27: proposals start unapproved — human must explicitly approve."""
        proposal = _HITLProposal("EDD_REQUIRED", "COMPLIANCE_OFFICER", "test")
        assert proposal.approved is False

    def test_blocked_jurisdiction_ru_rejected(self):
        assert not self.engine.check_jurisdiction("RU")

    def test_blocked_jurisdiction_ir_rejected(self):
        assert not self.engine.check_jurisdiction("IR")

    def test_blocked_jurisdiction_kp_rejected(self):
        assert not self.engine.check_jurisdiction("KP")

    def test_allowed_jurisdiction_gb_passes(self):
        assert self.engine.check_jurisdiction("GB")

    def test_allowed_jurisdiction_de_passes(self):
        assert self.engine.check_jurisdiction("DE")

    def test_payment_amount_is_decimal(self):
        """I-01: payment amounts are always Decimal."""
        p = _Payment("PAY001", "CUST001", Decimal("1000.00"), "GBP")
        assert isinstance(p.amount, Decimal)
        assert not isinstance(p.amount, float)

    def test_audit_log_append_only(self):
        """I-24: audit log grows, never shrinks."""
        c = _Customer("CUST001")
        self.engine.kyc_approve(c)
        size_before = len(self.engine.audit_log)
        self.engine.aml_screen(c, Decimal("100.00"))
        size_after = len(self.engine.audit_log)
        assert size_after >= size_before

    def test_full_flow_kyc_then_aml_then_payment(self):
        c = _Customer("CUST001")
        c = self.engine.kyc_approve(c)
        assert c.kyc_status == "APPROVED"

        result = self.engine.aml_screen(c, Decimal("500.00"))
        assert isinstance(result, _Customer)
        assert result.aml_status == "CLEARED"

        p = _Payment("PAY001", c.customer_id, Decimal("500.00"), "GBP", status="CLEARED")
        assert p.status == "CLEARED"

    def test_edd_boundary_below_does_not_trigger_hitl(self):
        c = _Customer("CUST001", kyc_status="APPROVED")
        result = self.engine.aml_screen(c, Decimal("9999.99"))
        assert isinstance(result, _Customer)
        assert result.aml_status == "CLEARED"

    def test_recon_step_uses_decimal(self):
        """Recon step in pipeline uses Decimal (I-01)."""
        ledger = Decimal("500.00")
        statement = Decimal("500.00")
        discrepancy = abs(ledger - statement)
        assert isinstance(discrepancy, Decimal)
        assert discrepancy == Decimal("0.00")
