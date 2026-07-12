"""
Banking Engine — HITL Gate Enforcement
Sprint B-5 | I-27: AI PROPOSES only; humans DECIDE.
EU AI Act Art.14: human oversight required at L3+ decisions.

Gate lifecycle:  propose() → PENDING → approve() → APPROVED
                                     → reject()  → REJECTED
                                     → timeout   → EXPIRED

No auto-approve path exists. Agents may only propose(); only humans may
call approve() or reject(). BDSL thresholds are PLACEHOLDER pending
MLRO/CRO sign-off and are NOT encoded here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
import uuid

# ---------------------------------------------------------------------------
# Audit hook (Protocol DI — injected at service startup, None in unit tests)
# ---------------------------------------------------------------------------

# Signature: (entity_type, entity_id, from_state, to_state, actor, metadata) → event_id
AuditFn = Callable[[str, str, str, str, str, dict[str, Any] | None], str]

_audit_fn: AuditFn | None = None


def set_audit_fn(fn: AuditFn | None) -> None:
    """Wire up the audit writer (called at service startup or in test fixtures)."""
    global _audit_fn  # noqa: PLW0603
    _audit_fn = fn


def _emit(
    entity_id: str,
    from_status: str,
    to_status: str,
    actor: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit an audit record if an audit function is configured."""
    if _audit_fn is not None:
        _audit_fn("hitl_gate", entity_id, from_status, to_status, actor, metadata)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GateStatus(str, Enum):
    """Lifecycle states of an HITL gate proposal."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class HITLGateType(str, Enum):
    """
    Gate types requiring human sign-off.
    BDSL numeric thresholds: PLACEHOLDER — pending MLRO/CRO sign-off.
    """

    SAR_FILING = "SAR_filing"
    AML_THRESHOLD_CHANGE = "AML_threshold_change"
    SANCTIONS_REVERSAL = "sanctions_reversal"
    PEP_ONBOARDING = "PEP_onboarding"


# ---------------------------------------------------------------------------
# Gate configuration
# ---------------------------------------------------------------------------

# Timeout windows: gate auto-expires (not auto-approves) on breach.
GATE_TIMEOUTS: dict[HITLGateType, timedelta] = {
    HITLGateType.SAR_FILING: timedelta(hours=24),
    HITLGateType.AML_THRESHOLD_CHANGE: timedelta(hours=4),
    HITLGateType.SANCTIONS_REVERSAL: timedelta(hours=1),
    HITLGateType.PEP_ONBOARDING: timedelta(hours=48),
}

# Required human autonomy level to RESOLVE each gate.
# L4 = Human Only (MLRO / CEO). Agents at any level may PROPOSE.
GATE_REQUIRED_LEVEL: dict[HITLGateType, int] = {
    HITLGateType.SAR_FILING: 4,  # MLRO sign-off
    HITLGateType.AML_THRESHOLD_CHANGE: 4,  # MLRO + CEO
    HITLGateType.SANCTIONS_REVERSAL: 4,  # MLRO + CEO
    HITLGateType.PEP_ONBOARDING: 4,  # MLRO
}


# ---------------------------------------------------------------------------
# Proposal dataclass
# ---------------------------------------------------------------------------


@dataclass
class HITLProposal:
    """
    An HITL gate proposal — always created in PENDING state.

    Fields
    ------
    gate_id         UUID4 string identifying this proposal.
    gate_type       Which compliance gate is being triggered.
    proposing_agent Name/ID of the agent making the proposal.
    proposal_payload Structured payload describing the proposed action.
    status          Current lifecycle state (PENDING on creation).
    created_at      UTC timestamp of proposal creation.
    resolved_at     UTC timestamp when status changed from PENDING (or None).
    resolved_by     Human identifier who resolved the gate (or None).
    expires_at      Computed in __post_init__ from created_at + gate timeout.
    """

    gate_id: str
    gate_type: HITLGateType
    proposing_agent: str
    proposal_payload: dict[str, Any]
    status: GateStatus = GateStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    def __post_init__(self) -> None:
        self.expires_at: datetime = self.created_at + GATE_TIMEOUTS[self.gate_type]

    def is_expired(self) -> bool:
        """True if the gate window has closed and the proposal is unresolved."""
        return datetime.now(UTC) > self.expires_at

    def refresh_status(self) -> GateStatus:
        """
        Transition PENDING → EXPIRED if the timeout has elapsed.

        Idempotent on already-resolved proposals. Emits an audit record on
        the PENDING → EXPIRED transition.
        """
        if self.status == GateStatus.PENDING and self.is_expired():
            prev = self.status.value
            self.status = GateStatus.EXPIRED
            _emit(
                self.gate_id,
                prev,
                GateStatus.EXPIRED.value,
                "system:timeout",
                {"gate_type": self.gate_type.value},
            )
        return self.status


# ---------------------------------------------------------------------------
# Public gate operations
# ---------------------------------------------------------------------------


def propose(
    gate_type: HITLGateType,
    proposing_agent: str,
    payload: dict[str, Any],
) -> HITLProposal:
    """
    Create a new PENDING gate proposal.

    Any agent at any autonomy level may call this.
    The returned proposal is NEVER auto-approved — a human must call approve().
    I-27: AI PROPOSES; human DECIDES.
    """
    proposal = HITLProposal(
        gate_id=str(uuid.uuid4()),
        gate_type=gate_type,
        proposing_agent=proposing_agent,
        proposal_payload=payload,
    )
    _emit(
        proposal.gate_id,
        "NONE",
        GateStatus.PENDING.value,
        proposing_agent,
        {"gate_type": gate_type.value},
    )
    return proposal


def approve(proposal: HITLProposal, approver: str) -> HITLProposal:
    """
    An authorised human approves a PENDING gate.

    Returns the proposal unchanged (with status EXPIRED) if the timeout has
    already passed — expired proposals cannot be approved. No-op on already-
    resolved proposals.
    """
    proposal.refresh_status()
    if proposal.status != GateStatus.PENDING:
        return proposal
    prev = proposal.status.value
    proposal.status = GateStatus.APPROVED
    proposal.resolved_at = datetime.now(UTC)
    proposal.resolved_by = approver
    _emit(
        proposal.gate_id,
        prev,
        GateStatus.APPROVED.value,
        approver,
        {"gate_type": proposal.gate_type.value},
    )
    return proposal


def reject(proposal: HITLProposal, approver: str) -> HITLProposal:
    """
    An authorised human rejects a PENDING gate.

    No-op if the proposal is already resolved or expired.
    """
    proposal.refresh_status()
    if proposal.status != GateStatus.PENDING:
        return proposal
    prev = proposal.status.value
    proposal.status = GateStatus.REJECTED
    proposal.resolved_at = datetime.now(UTC)
    proposal.resolved_by = approver
    _emit(
        proposal.gate_id,
        prev,
        GateStatus.REJECTED.value,
        approver,
        {"gate_type": proposal.gate_type.value},
    )
    return proposal
