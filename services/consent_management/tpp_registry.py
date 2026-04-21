"""
services/consent_management/tpp_registry.py
TPP Registry Service
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65, FCA PERG 15.5, PSR 2017 Reg.112-120
Trust Zone: RED

register_tpp — register new TPP (SHA-256 ID, I-02 jurisdiction check).
suspend_tpp — returns HITLProposal (I-27: L4 HITL).
deregister_tpp — returns HITLProposal (I-27: L4 HITL).
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import logging

from services.consent_management.models import (
    BLOCKED_JURISDICTIONS,
    HITLProposal,
    InMemoryTPPRegistry,
    TPPRegistration,
    TPPRegistryPort,
    TPPStatus,
    TPPType,
)

logger = logging.getLogger(__name__)


def _make_tpp_id(name: str, eidas_cert_id: str) -> str:
    """Generate SHA-256-based TPP ID."""
    raw = f"{name}:{eidas_cert_id}"
    return f"tpp_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


class TPPRegistryService:
    """TPP Registry Service.

    Protocol DI: TPPRegistryPort.
    I-02: Blocks sanctioned jurisdictions.
    I-27: Suspension and deregistration return HITLProposal.
    """

    def __init__(self, tpp_registry: TPPRegistryPort | None = None) -> None:
        """Initialise with injectable registry port (default: InMemory stub)."""
        self._registry: TPPRegistryPort = tpp_registry or InMemoryTPPRegistry()

    def register_tpp(
        self,
        name: str,
        eidas_cert_id: str,
        tpp_type: TPPType,
        jurisdiction: str,
        competent_authority: str,
    ) -> TPPRegistration:
        """Register a new TPP.

        I-02: Raises ValueError for blocked jurisdictions.
        SHA-256-based TPP ID.

        Args:
            name: TPP legal name.
            eidas_cert_id: eIDAS certificate ID.
            tpp_type: AISP / PISP / BOTH.
            jurisdiction: ISO country code (I-02: must not be blocked).
            competent_authority: Regulatory authority (e.g. FCA).

        Returns:
            TPPRegistration with REGISTERED status.

        Raises:
            ValueError: If jurisdiction is in BLOCKED_JURISDICTIONS (I-02).
        """
        if jurisdiction.upper() in BLOCKED_JURISDICTIONS:
            raise ValueError(
                f"Jurisdiction '{jurisdiction}' is blocked under I-02 sanctions policy "
                f"(BLOCKED_JURISDICTIONS: {', '.join(sorted(BLOCKED_JURISDICTIONS))})"
            )

        tpp_id = _make_tpp_id(name, eidas_cert_id)
        registered_at = datetime.now(UTC).isoformat()

        tpp = TPPRegistration(
            tpp_id=tpp_id,
            name=name,
            eidas_cert_id=eidas_cert_id,
            tpp_type=tpp_type,
            status=TPPStatus.REGISTERED,
            registered_at=registered_at,
            jurisdiction=jurisdiction,
            competent_authority=competent_authority,
        )
        self._registry.register(tpp)
        logger.info("TPP registered tpp_id=%s name=%s jurisdiction=%s", tpp_id, name, jurisdiction)
        return tpp

    def get_tpp(self, tpp_id: str) -> TPPRegistration | None:
        """Retrieve a TPP by ID.

        Args:
            tpp_id: TPP identifier.

        Returns:
            TPPRegistration or None.
        """
        return self._registry.get(tpp_id)

    def list_active_tpps(self, tpp_type: TPPType | None = None) -> list[TPPRegistration]:
        """List active (REGISTERED) TPPs, optionally filtered by type.

        Args:
            tpp_type: Optional filter by TPPType.

        Returns:
            List of active TPPRegistration records.
        """
        active = self._registry.list_active()
        if tpp_type is not None:
            active = [t for t in active if t.tpp_type == tpp_type or t.tpp_type == TPPType.BOTH]
        return active

    def suspend_tpp(self, tpp_id: str, reason: str, operator: str) -> HITLProposal:
        """Return HITL proposal for TPP suspension.

        I-27: Suspension is an L4 operation requiring COMPLIANCE_OFFICER approval.

        Args:
            tpp_id: TPP to suspend.
            reason: Reason for suspension.
            operator: Requesting operator.

        Returns:
            HITLProposal requiring COMPLIANCE_OFFICER approval.
        """
        logger.warning(
            "TPP suspension requested tpp_id=%s operator=%s reason=%s — returning HITL (I-27)",
            tpp_id,
            operator,
            reason,
        )
        return HITLProposal(
            action="SUSPEND_TPP",
            entity_id=tpp_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"TPP suspension is irreversible L4 action (I-27, PSR 2017 Reg.116): "
                f"tpp_id={tpp_id} reason={reason} operator={operator}"
            ),
        )

    def deregister_tpp(self, tpp_id: str, reason: str, operator: str) -> HITLProposal:
        """Return HITL proposal for TPP deregistration.

        I-27: Deregistration is an L4 operation requiring COMPLIANCE_OFFICER approval.

        Args:
            tpp_id: TPP to deregister.
            reason: Reason for deregistration.
            operator: Requesting operator.

        Returns:
            HITLProposal requiring COMPLIANCE_OFFICER approval.
        """
        logger.warning(
            "TPP deregistration requested tpp_id=%s operator=%s — returning HITL (I-27)",
            tpp_id,
            operator,
        )
        return HITLProposal(
            action="DEREGISTER_TPP",
            entity_id=tpp_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"TPP deregistration is irreversible L4 action (I-27, PSR 2017 Reg.117): "
                f"tpp_id={tpp_id} reason={reason} operator={operator}"
            ),
        )
