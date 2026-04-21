"""
services/consent_management/psd2_flow_handler.py
PSD2 Flow Handler — AISP / PISP / CBPII
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65-67, RTS on SCA Art.29-32, FCA PERG 15.5 (AISP/PISP)
Trust Zone: RED

initiate_aisp_flow — creates PENDING consent.
complete_aisp_flow — activates or revokes consent.
initiate_pisp_payment — returns HITLProposal (I-27: always L4).
handle_cbpii_check — confirmation of funds (EDD threshold £10k, I-04).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import logging

from services.consent_management.models import (
    AuditLogPort,
    ConsentAuditEvent,
    ConsentGrant,
    ConsentScope,
    ConsentStatus,
    ConsentStorePort,
    ConsentType,
    HITLProposal,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
    TPPRegistryPort,
    TPPStatus,
)

logger = logging.getLogger(__name__)

# I-04: EDD threshold
EDD_THRESHOLD = Decimal("10000")


def _make_consent_id(prefix: str, customer_id: str, tpp_id: str, ts: str) -> str:
    """Generate SHA-256-based consent ID."""
    raw = f"{prefix}:{customer_id}:{tpp_id}:{ts}"
    return f"cns_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def _make_event_id(consent_id: str, event_type: str, ts: str) -> str:
    """Generate SHA-256-based event ID."""
    raw = f"{consent_id}:{event_type}:{ts}"
    return f"evt_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


class PSD2FlowHandler:
    """PSD2 AISP/PISP/CBPII flow orchestrator.

    Protocol DI: ConsentStorePort, TPPRegistryPort, AuditLogPort.
    I-27: PISP payment initiation always returns HITLProposal.
    I-04: CBPII check blocks amounts >= £10k (EDD threshold).
    """

    def __init__(
        self,
        consent_store: ConsentStorePort | None = None,
        tpp_registry: TPPRegistryPort | None = None,
        audit_log: AuditLogPort | None = None,
    ) -> None:
        """Initialise with injectable ports (default: InMemory stubs)."""
        self._store: ConsentStorePort = consent_store or InMemoryConsentStore()
        self._tpp_registry: TPPRegistryPort = tpp_registry or InMemoryTPPRegistry()
        self._audit: AuditLogPort = audit_log or InMemoryAuditLog()

    def initiate_aisp_flow(
        self,
        customer_id: str,
        tpp_id: str,
        scopes: list[ConsentScope],
        redirect_uri: str,
        ttl_days: int = 90,
    ) -> ConsentGrant:
        """Initiate AISP consent flow — creates PENDING consent.

        Customer authentication required before activation.
        PSD2 Art.65: AISP access to account data.

        Args:
            customer_id: Customer identifier.
            tpp_id: TPP identifier (must be REGISTERED).
            scopes: Data scopes requested (ACCOUNTS/BALANCES/TRANSACTIONS).
            redirect_uri: TPP callback URI.
            ttl_days: Consent validity in days (default 90).

        Returns:
            ConsentGrant with PENDING status.

        Raises:
            ValueError: If TPP is not REGISTERED.
        """
        tpp = self._tpp_registry.get(tpp_id)
        if tpp is None or tpp.status != TPPStatus.REGISTERED:
            raise ValueError(
                f"TPP '{tpp_id}' is not REGISTERED — cannot initiate AISP flow (PSD2 Art.65)"
            )

        now = datetime.now(UTC)
        granted_at = now.isoformat()
        expires_at = (now + timedelta(days=ttl_days)).isoformat()
        consent_id = _make_consent_id("aisp", customer_id, tpp_id, granted_at)

        consent = ConsentGrant(
            consent_id=consent_id,
            customer_id=customer_id,
            tpp_id=tpp_id,
            consent_type=ConsentType.AISP,
            scopes=scopes,
            granted_at=granted_at,
            expires_at=expires_at,
            status=ConsentStatus.PENDING,
            redirect_uri=redirect_uri,
        )
        self._store.save(consent)

        self._audit.append(
            ConsentAuditEvent(
                event_id=_make_event_id(consent_id, "AISP_INITIATED", granted_at),
                consent_id=consent_id,
                event_type="AISP_INITIATED",
                actor=customer_id,
                timestamp=granted_at,
                details=f"AISP flow initiated tpp={tpp_id} scopes={scopes}",
            )
        )
        logger.info("AISP flow initiated consent_id=%s tpp=%s", consent_id, tpp_id)
        return consent

    def complete_aisp_flow(self, consent_id: str, customer_approved: bool) -> ConsentGrant:
        """Complete AISP flow — activates or revokes consent based on customer decision.

        Args:
            consent_id: Pending consent to complete.
            customer_approved: True if customer approved, False to revoke.

        Returns:
            Updated ConsentGrant (ACTIVE or REVOKED).

        Raises:
            ValueError: If consent not found.
        """
        existing = self._store.get(consent_id)
        if existing is None:
            raise ValueError(f"Consent '{consent_id}' not found")

        new_status = ConsentStatus.ACTIVE if customer_approved else ConsentStatus.REVOKED
        ts = datetime.now(UTC).isoformat()

        updated = ConsentGrant(
            consent_id=existing.consent_id,
            customer_id=existing.customer_id,
            tpp_id=existing.tpp_id,
            consent_type=existing.consent_type,
            scopes=existing.scopes,
            granted_at=existing.granted_at,
            expires_at=existing.expires_at,
            status=new_status,
            transaction_limit=existing.transaction_limit,
            redirect_uri=existing.redirect_uri,
        )
        self._store.save(updated)  # I-24: append new version

        event_type = "AISP_COMPLETED" if customer_approved else "AISP_REJECTED"
        self._audit.append(
            ConsentAuditEvent(
                event_id=_make_event_id(consent_id, event_type, ts),
                consent_id=consent_id,
                event_type=event_type,
                actor=existing.customer_id,
                timestamp=ts,
                details=f"AISP flow completed approved={customer_approved} status={new_status}",
            )
        )
        logger.info("AISP flow completed consent_id=%s approved=%s", consent_id, customer_approved)
        return updated

    def initiate_pisp_payment(self, consent_id: str, amount: Decimal, payee: str) -> HITLProposal:
        """Initiate PISP payment — always returns HITLProposal (I-27).

        Payment initiation is always L4 HITL per I-27 (irreversible financial action).
        PSD2 Art.66: PISP payment initiation requires SCA.

        Args:
            consent_id: Active PISP consent.
            amount: Payment amount as Decimal (I-01).
            payee: Payee identifier.

        Returns:
            HITLProposal requiring COMPLIANCE_OFFICER approval.
        """
        logger.warning(
            "PISP payment initiation consent_id=%s amount=%s — returning HITL (I-27)",
            consent_id,
            amount,
        )
        return HITLProposal(
            action="INITIATE_PISP_PAYMENT",
            entity_id=consent_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=(
                f"PISP payment initiation is L4 HITL (I-27, PSD2 Art.66): "
                f"consent_id={consent_id} amount={amount} payee={payee}"
            ),
        )

    def handle_cbpii_check(self, consent_id: str, amount: Decimal) -> bool:
        """Handle CBPII confirmation of funds check.

        I-04: Amounts >= £10k (EDD threshold) raise ValueError.
        PSD2 Art.65(4): Confirmation of funds — yes/no response.

        Args:
            consent_id: Active CBPII consent.
            amount: Amount to check as Decimal (I-01).

        Returns:
            True if funds available (stub: always True for valid consent).

        Raises:
            ValueError: If amount >= EDD threshold £10k (I-04).
        """
        if amount >= EDD_THRESHOLD:
            raise ValueError(
                f"CBPII check amount {amount} >= EDD threshold £{EDD_THRESHOLD} — "
                f"requires Enhanced Due Diligence (I-04, PSD2 Art.65(4))"
            )

        consent = self._store.get(consent_id)
        if consent is None:
            return False

        now = datetime.now(UTC).isoformat()
        if consent.status != ConsentStatus.ACTIVE or consent.expires_at <= now:
            return False

        logger.info("CBPII check consent_id=%s amount=%s — funds confirmed", consent_id, amount)
        return True
