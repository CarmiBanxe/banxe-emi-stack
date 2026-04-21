"""
services/consent_management/consent_engine.py
Consent Management Engine
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65-67, RTS on SCA Art.29-32, PSR 2017 Reg.112-120
Trust Zone: RED

grant_consent — creates PSD2 consent grant.
revoke_consent — returns HITLProposal (I-27: irreversible).
validate_consent — checks status + scope + expiry.
Append-only audit (I-24). SHA-256 IDs. UTC timestamps.
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


def _make_consent_id(customer_id: str, tpp_id: str, ts: str) -> str:
    """Generate SHA-256-based consent ID (I-24)."""
    raw = f"{customer_id}:{tpp_id}:{ts}"
    return f"cns_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def _make_event_id(consent_id: str, event_type: str, ts: str) -> str:
    """Generate SHA-256-based event ID."""
    raw = f"{consent_id}:{event_type}:{ts}"
    return f"evt_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


class ConsentEngine:
    """PSD2 Consent lifecycle engine.

    Protocol DI: ConsentStorePort, TPPRegistryPort, AuditLogPort.
    All mutations append-only (I-24). Revocation returns HITLProposal (I-27).
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

    def grant_consent(
        self,
        customer_id: str,
        tpp_id: str,
        consent_type: ConsentType,
        scopes: list[ConsentScope],
        ttl_days: int = 90,
        transaction_limit: Decimal | None = None,
        redirect_uri: str = "https://tpp.example.com/callback",
    ) -> ConsentGrant:
        """Grant PSD2 consent to a TPP.

        Validates TPP is REGISTERED. Creates ConsentGrant with SHA-256 ID.
        Appends audit event (I-24). TTL default 90 days (PSD2 Art.65).

        Args:
            customer_id: Customer identifier.
            tpp_id: TPP identifier (must be REGISTERED).
            consent_type: AISP / PISP / CBPII.
            scopes: List of ConsentScope values.
            ttl_days: Consent validity in days (default 90).
            transaction_limit: Optional Decimal limit (I-01).
            redirect_uri: TPP callback URI.

        Returns:
            ConsentGrant with ACTIVE status.

        Raises:
            ValueError: If TPP is not REGISTERED.
        """
        tpp = self._tpp_registry.get(tpp_id)
        if tpp is None or tpp.status != TPPStatus.REGISTERED:
            raise ValueError(
                f"TPP '{tpp_id}' is not REGISTERED — cannot grant consent (PSD2 Art.65)"
            )

        now = datetime.now(UTC)
        granted_at = now.isoformat()
        expires_at = (now + timedelta(days=ttl_days)).isoformat()
        consent_id = _make_consent_id(customer_id, tpp_id, granted_at)

        consent = ConsentGrant(
            consent_id=consent_id,
            customer_id=customer_id,
            tpp_id=tpp_id,
            consent_type=consent_type,
            scopes=scopes,
            granted_at=granted_at,
            expires_at=expires_at,
            status=ConsentStatus.ACTIVE,
            transaction_limit=transaction_limit,
            redirect_uri=redirect_uri,
        )
        self._store.save(consent)

        # Append audit event (I-24)
        event = ConsentAuditEvent(
            event_id=_make_event_id(consent_id, "GRANTED", granted_at),
            consent_id=consent_id,
            event_type="CONSENT_GRANTED",
            actor=customer_id,
            timestamp=granted_at,
            details=f"Consent granted to TPP {tpp_id} type={consent_type} scopes={scopes}",
        )
        self._audit.append(event)

        logger.info(
            "Consent granted consent_id=%s tpp=%s customer=%s", consent_id, tpp_id, customer_id
        )
        return consent

    def revoke_consent(self, consent_id: str, actor: str) -> HITLProposal:
        """Return HITL proposal for consent revocation.

        I-27: Revocation is irreversible — always L4 HITL.
        Revocation immediately updates consent status to REVOKED (pending approval).

        Args:
            consent_id: Consent to revoke.
            actor: Person requesting revocation.

        Returns:
            HITLProposal requiring human approval.
        """
        logger.warning(
            "Consent revocation requested consent_id=%s actor=%s — returning HITL (I-27)",
            consent_id,
            actor,
        )
        return HITLProposal(
            action="REVOKE_CONSENT",
            entity_id=consent_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=f"Consent revocation is irreversible (I-27, PSD2 Art.66): consent_id={consent_id} actor={actor}",
        )

    def get_active_consents(self, customer_id: str) -> list[ConsentGrant]:
        """Get all ACTIVE (non-expired) consents for a customer.

        Args:
            customer_id: Customer identifier.

        Returns:
            List of active ConsentGrant records.
        """
        now = datetime.now(UTC).isoformat()
        consents = self._store.list_by_customer(customer_id)
        # Deduplicate: take latest version per consent_id
        seen: dict[str, ConsentGrant] = {}
        for c in consents:
            seen[c.consent_id] = c
        return [c for c in seen.values() if c.status == ConsentStatus.ACTIVE and c.expires_at > now]

    def validate_consent(self, consent_id: str, required_scope: ConsentScope) -> bool:
        """Validate consent is active, not expired, and covers required scope.

        Args:
            consent_id: Consent to validate.
            required_scope: The scope that must be present.

        Returns:
            True if consent is valid for the scope.
        """
        consent = self._store.get(consent_id)
        if consent is None:
            return False
        if consent.status != ConsentStatus.ACTIVE:
            return False
        now = datetime.now(UTC).isoformat()
        if consent.expires_at <= now:
            return False
        return required_scope in consent.scopes
