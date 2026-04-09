"""
services/hitl/org_roles.py — Org-Role HITL Enforcement Layer
IL-065 | banxe-emi-stack
Created: 2026-04-09

Implements role-based authority checks for HITL decision gates.

Source of truth: banxe-architecture/HITL-MATRIX.yaml
Human-readable:  banxe-architecture/docs/ORG-STRUCTURE.md

Key invariants enforced:
  I-27: No autonomous model updates — CRO + CEO approval required.
  I-04: EDD + HITL mandatory for ≥£10k (individual) / ≥£50k (corporate).
  EU AI Act Art.14: meaningful human oversight of high-risk AI decisions.
  SM&CR: SAR filing, PEP approval, sanctions reversal → MLRO non-delegable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ── Org roles (SM&CR aligned) ─────────────────────────────────────────────────


class OrgRole(str, Enum):
    """
    Roles that can act as HITL approvers.
    Mirrors HITL-MATRIX.yaml roles section.
    """

    CEO = "CEO"  # SMF1
    CFO = "CFO"  # SMF2
    CRO = "CRO"  # SMF4
    INTERNAL_AUDITOR = "INTERNAL_AUDITOR"  # SMF5
    MLRO = "MLRO"  # SMF17
    COO = "COO"  # SMF24
    CTO = "CTO"  # SMF26
    COMPLIANCE_OFFICER = "COMPLIANCE_OFFICER"  # Certified, not SMF
    OPERATOR = "OPERATOR"  # Operations staff (within limits)


# ── HITL trigger types ────────────────────────────────────────────────────────


class HITLTrigger(str, Enum):
    """
    Decision triggers — map to HITL-MATRIX.yaml gate ids.
    New triggers must have a corresponding gate in the matrix.
    """

    SAR_REQUIRED = "SAR_REQUIRED"  # HITL-001
    EDD_REQUIRED = "EDD_REQUIRED"  # HITL-002
    SANCTIONS_HIT = "SANCTIONS_HIT"  # HITL-003 (auto-block)
    SANCTIONS_REVERSAL_REQUEST = "SANCTIONS_REVERSAL_REQUEST"  # HITL-004
    AML_CUSTOMER_BLOCK = "AML_CUSTOMER_BLOCK"  # HITL-005
    KYC_HIGH_RISK_REJECTION = "KYC_HIGH_RISK_REJECTION"  # HITL-006
    PEP_ONBOARDING = "PEP_ONBOARDING"  # HITL-007
    SAR_RETRACTION_REQUEST = "SAR_RETRACTION_REQUEST"  # HITL-008
    FRAUD_HIGH = "FRAUD_HIGH"  # HITL-009
    FCA_REGDATA_SUBMISSION = "FCA_REGDATA_SUBMISSION"  # HITL-010
    SAFEGUARDING_SHORTFALL = "SAFEGUARDING_SHORTFALL"  # HITL-011
    AML_THRESHOLD_CHANGE = "AML_THRESHOLD_CHANGE"  # HITL-012
    PRODUCTION_DEPLOY = "PRODUCTION_DEPLOY"  # HITL-013
    AI_MODEL_UPDATE = "AI_MODEL_UPDATE"  # HITL-014
    SECURITY_INCIDENT_CRITICAL = "SECURITY_INCIDENT_CRITICAL"  # HITL-015
    LARGE_TRANSACTION = "LARGE_TRANSACTION"  # HITL-016
    NEW_PRODUCT_LAUNCH = "NEW_PRODUCT_LAUNCH"  # HITL-017


# ── Gate definition ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HITLGate:
    """
    Defines the approval requirements for a single HITL trigger.

    required_roles: ALL of these must approve (AND logic).
    any_of_roles:   ONE of these is sufficient (OR logic).
    auto_allowed:   If True, AI may proceed without human approval
                    (used only for SANCTIONS_HIT auto-block; never for approvals).
    sla_hours:      SLA before auto-escalation / FCA alert (0 = immediate).
    fca_basis:      Regulatory reference.
    """

    gate_id: str
    trigger: HITLTrigger
    required_roles: tuple[OrgRole, ...]  # ALL required (AND)
    any_of_roles: tuple[OrgRole, ...]  # ONE required (OR)
    sla_hours: int
    auto_allowed: bool
    fca_basis: str
    severity: str  # critical | high | medium | low

    def approvers_needed(self) -> set[OrgRole]:
        """Return minimum set of roles needed to satisfy this gate."""
        return set(self.required_roles)

    def is_satisfied_by(self, approver_roles: set[OrgRole]) -> bool:
        """
        Returns True if the given set of approver roles satisfies this gate.

        Logic:
          - All required_roles must be present (AND).
          - At least one of any_of_roles must be present (OR), unless empty.
        """
        all_required = all(r in approver_roles for r in self.required_roles)
        if not self.any_of_roles:
            return all_required
        any_satisfied = any(r in approver_roles for r in self.any_of_roles)
        return all_required and any_satisfied

    def missing_roles(self, approver_roles: set[OrgRole]) -> list[OrgRole]:
        """
        Returns list of roles still needed to satisfy this gate.
        Useful for generating actionable error messages.
        """
        missing = [r for r in self.required_roles if r not in approver_roles]
        if self.any_of_roles and not any(r in approver_roles for r in self.any_of_roles):
            # None of the OR options are present — show first one as representative
            missing.extend(list(self.any_of_roles[:1]))
        return missing


# ── Gate registry ─────────────────────────────────────────────────────────────

# Maps HITLTrigger → HITLGate (single source of truth)
GATE_REGISTRY: dict[HITLTrigger, HITLGate] = {
    HITLTrigger.SAR_REQUIRED: HITLGate(
        gate_id="HITL-001",
        trigger=HITLTrigger.SAR_REQUIRED,
        required_roles=(OrgRole.MLRO,),
        any_of_roles=(),
        sla_hours=4,
        auto_allowed=False,
        fca_basis="POCA 2002 s.330; MLR 2017 Reg.19",
        severity="critical",
    ),
    HITLTrigger.EDD_REQUIRED: HITLGate(
        gate_id="HITL-002",
        trigger=HITLTrigger.EDD_REQUIRED,
        required_roles=(),
        any_of_roles=(OrgRole.MLRO, OrgRole.COMPLIANCE_OFFICER),
        sla_hours=24,
        auto_allowed=False,
        fca_basis="MLR 2017 Reg.28; I-04",
        severity="high",
    ),
    HITLTrigger.SANCTIONS_HIT: HITLGate(
        gate_id="HITL-003",
        trigger=HITLTrigger.SANCTIONS_HIT,
        required_roles=(),
        any_of_roles=(),
        sla_hours=0,
        auto_allowed=True,  # BLOCK is automatic; no human needed to block
        fca_basis="SAMLA 2018; OFSI guidance; I-15",
        severity="critical",
    ),
    HITLTrigger.SANCTIONS_REVERSAL_REQUEST: HITLGate(
        gate_id="HITL-004",
        trigger=HITLTrigger.SANCTIONS_REVERSAL_REQUEST,
        required_roles=(OrgRole.MLRO, OrgRole.CEO),
        any_of_roles=(),
        sla_hours=2,
        auto_allowed=False,
        fca_basis="SAMLA 2018 s.20; OFSI consent",
        severity="critical",
    ),
    HITLTrigger.AML_CUSTOMER_BLOCK: HITLGate(
        gate_id="HITL-005",
        trigger=HITLTrigger.AML_CUSTOMER_BLOCK,
        required_roles=(OrgRole.MLRO,),
        any_of_roles=(),
        sla_hours=4,
        auto_allowed=False,
        fca_basis="MLR 2017 Reg.27; POCA 2002",
        severity="critical",
    ),
    HITLTrigger.KYC_HIGH_RISK_REJECTION: HITLGate(
        gate_id="HITL-006",
        trigger=HITLTrigger.KYC_HIGH_RISK_REJECTION,
        required_roles=(),
        any_of_roles=(OrgRole.MLRO, OrgRole.COMPLIANCE_OFFICER),
        sla_hours=24,
        auto_allowed=False,
        fca_basis="MLR 2017 Reg.21; FCA SYSC 6.3",
        severity="high",
    ),
    HITLTrigger.PEP_ONBOARDING: HITLGate(
        gate_id="HITL-007",
        trigger=HITLTrigger.PEP_ONBOARDING,
        required_roles=(OrgRole.MLRO, OrgRole.CEO),
        any_of_roles=(),
        sla_hours=48,
        auto_allowed=False,
        fca_basis="MLR 2017 Reg.35",
        severity="critical",
    ),
    HITLTrigger.SAR_RETRACTION_REQUEST: HITLGate(
        gate_id="HITL-008",
        trigger=HITLTrigger.SAR_RETRACTION_REQUEST,
        required_roles=(OrgRole.MLRO, OrgRole.CEO),
        any_of_roles=(),
        sla_hours=4,
        auto_allowed=False,
        fca_basis="POCA 2002 s.330",
        severity="critical",
    ),
    HITLTrigger.FRAUD_HIGH: HITLGate(
        gate_id="HITL-009",
        trigger=HITLTrigger.FRAUD_HIGH,
        required_roles=(),
        any_of_roles=(OrgRole.MLRO, OrgRole.COMPLIANCE_OFFICER, OrgRole.OPERATOR),
        sla_hours=24,
        auto_allowed=False,
        fca_basis="PSR APP 2024; EU AI Act Art.14",
        severity="high",
    ),
    HITLTrigger.FCA_REGDATA_SUBMISSION: HITLGate(
        gate_id="HITL-010",
        trigger=HITLTrigger.FCA_REGDATA_SUBMISSION,
        required_roles=(OrgRole.CFO,),
        any_of_roles=(),
        sla_hours=168,
        auto_allowed=False,
        fca_basis="CASS 15.12.4R; FCA PS7/24 FIN060",
        severity="high",
    ),
    HITLTrigger.SAFEGUARDING_SHORTFALL: HITLGate(
        gate_id="HITL-011",
        trigger=HITLTrigger.SAFEGUARDING_SHORTFALL,
        required_roles=(OrgRole.CFO, OrgRole.MLRO),
        any_of_roles=(),
        sla_hours=4,
        auto_allowed=False,
        fca_basis="CASS 7.15.17R; CASS 7.13.6R",
        severity="critical",
    ),
    HITLTrigger.AML_THRESHOLD_CHANGE: HITLGate(
        gate_id="HITL-012",
        trigger=HITLTrigger.AML_THRESHOLD_CHANGE,
        required_roles=(OrgRole.CRO, OrgRole.CEO),
        any_of_roles=(),
        sla_hours=168,
        auto_allowed=False,
        fca_basis="MLR 2017 Reg.18; I-27",
        severity="high",
    ),
    HITLTrigger.PRODUCTION_DEPLOY: HITLGate(
        gate_id="HITL-013",
        trigger=HITLTrigger.PRODUCTION_DEPLOY,
        required_roles=(OrgRole.CTO,),
        any_of_roles=(),
        sla_hours=24,
        auto_allowed=False,
        fca_basis="FCA SYSC 8.1",
        severity="medium",
    ),
    HITLTrigger.AI_MODEL_UPDATE: HITLGate(
        gate_id="HITL-014",
        trigger=HITLTrigger.AI_MODEL_UPDATE,
        required_roles=(OrgRole.CRO, OrgRole.CTO),
        any_of_roles=(),
        sla_hours=168,
        auto_allowed=False,
        fca_basis="EU AI Act Art.9; Art.17; I-27",
        severity="high",
    ),
    HITLTrigger.SECURITY_INCIDENT_CRITICAL: HITLGate(
        gate_id="HITL-015",
        trigger=HITLTrigger.SECURITY_INCIDENT_CRITICAL,
        required_roles=(OrgRole.CTO, OrgRole.CEO),
        any_of_roles=(),
        sla_hours=2,
        auto_allowed=False,
        fca_basis="FCA SYSC 8.1.1R; NIS Regulations 2018",
        severity="critical",
    ),
    HITLTrigger.LARGE_TRANSACTION: HITLGate(
        gate_id="HITL-016",
        trigger=HITLTrigger.LARGE_TRANSACTION,
        required_roles=(),
        any_of_roles=(OrgRole.COO, OrgRole.CFO),
        sla_hours=1,
        auto_allowed=False,
        fca_basis="MLR 2017 Reg.28; PSR 2017 Reg.71",
        severity="high",
    ),
    HITLTrigger.NEW_PRODUCT_LAUNCH: HITLGate(
        gate_id="HITL-017",
        trigger=HITLTrigger.NEW_PRODUCT_LAUNCH,
        required_roles=(OrgRole.CEO,),
        any_of_roles=(),
        sla_hours=720,
        auto_allowed=False,
        fca_basis="FCA PRIN 2A; FCA COBS 2; FCA Product Governance",
        severity="high",
    ),
}


# ── Approval result ───────────────────────────────────────────────────────────


@dataclass
class ApprovalResult:
    """
    Result of checking whether a set of approvers satisfies a HITL gate.
    """

    trigger: HITLTrigger
    gate_id: str
    approved: bool
    approver_roles: set[OrgRole]
    missing_roles: list[OrgRole]
    auto_allowed: bool
    sla_hours: int
    severity: str
    fca_basis: str
    message: str = field(init=False)

    def __post_init__(self) -> None:
        if self.auto_allowed:
            self.message = f"{self.gate_id}: auto-allowed (no human approval needed)"
        elif self.approved:
            roles_str = ", ".join(r.value for r in self.approver_roles)
            self.message = f"{self.gate_id}: approved by [{roles_str}] — SLA {self.sla_hours}h"
        else:
            missing_str = ", ".join(r.value for r in self.missing_roles)
            self.message = (
                f"{self.gate_id}: BLOCKED — missing approvers: [{missing_str}] ({self.fca_basis})"
            )


# ── OrgRoleChecker ────────────────────────────────────────────────────────────


class OrgRoleChecker:
    """
    Checks whether a given set of approver roles satisfies a HITL gate.

    Usage:
        checker = OrgRoleChecker()

        # Check if MLRO alone can approve a SAR filing
        result = checker.check(
            trigger=HITLTrigger.SAR_REQUIRED,
            approver_roles={OrgRole.MLRO},
        )
        assert result.approved is True

        # Check if OPERATOR can approve a SAR filing (must fail)
        result = checker.check(
            trigger=HITLTrigger.SAR_REQUIRED,
            approver_roles={OrgRole.OPERATOR},
        )
        assert result.approved is False
        assert OrgRole.MLRO in result.missing_roles
    """

    def check(
        self,
        trigger: HITLTrigger,
        approver_roles: set[OrgRole],
    ) -> ApprovalResult:
        """
        Check whether approver_roles satisfies the HITL gate for trigger.

        Args:
            trigger:        The decision trigger type.
            approver_roles: Set of roles of the person(s) attempting to approve.

        Returns:
            ApprovalResult with approved=True if gate satisfied.

        Raises:
            KeyError: If trigger has no registered gate (programming error).
        """
        gate = GATE_REGISTRY[trigger]

        if gate.auto_allowed:
            return ApprovalResult(
                trigger=trigger,
                gate_id=gate.gate_id,
                approved=True,
                approver_roles=approver_roles,
                missing_roles=[],
                auto_allowed=True,
                sla_hours=gate.sla_hours,
                severity=gate.severity,
                fca_basis=gate.fca_basis,
            )

        satisfied = gate.is_satisfied_by(approver_roles)
        missing = [] if satisfied else gate.missing_roles(approver_roles)

        return ApprovalResult(
            trigger=trigger,
            gate_id=gate.gate_id,
            approved=satisfied,
            approver_roles=approver_roles,
            missing_roles=missing,
            auto_allowed=False,
            sla_hours=gate.sla_hours,
            severity=gate.severity,
            fca_basis=gate.fca_basis,
        )

    def get_gate(self, trigger: HITLTrigger) -> HITLGate:
        """Retrieve gate definition for a trigger."""
        return GATE_REGISTRY[trigger]

    def all_gates(self) -> list[HITLGate]:
        """Return all registered HITL gates, sorted by gate_id."""
        return sorted(GATE_REGISTRY.values(), key=lambda g: g.gate_id)

    def gates_for_role(self, role: OrgRole) -> list[HITLGate]:
        """Return all gates where this role is required or sufficient."""
        result = []
        for gate in GATE_REGISTRY.values():
            if role in gate.required_roles or role in gate.any_of_roles:
                result.append(gate)
        return sorted(result, key=lambda g: g.gate_id)

    def critical_gates(self) -> list[HITLGate]:
        """Return all CRITICAL severity gates."""
        return [g for g in self.all_gates() if g.severity == "critical"]
