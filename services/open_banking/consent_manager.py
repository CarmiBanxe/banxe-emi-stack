"""
services/open_banking/consent_manager.py
IL-OBK-01 | Phase 15

Consent lifecycle: create / authorise / revoke (PSD2 RTS Art.10 — 90-day re-auth)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from services.open_banking.models import (
    AccountAccessType,
    ASPSPRegistryPort,
    Consent,
    ConsentStatus,
    ConsentStorePort,
    ConsentType,
    OBAuditTrailPort,
    _new_event,
)

_90_DAYS = timedelta(days=90)


class ConsentManager:
    """Manages PSD2 consent lifecycle: create, authorise, revoke."""

    def __init__(
        self,
        store: ConsentStorePort,
        registry: ASPSPRegistryPort,
        audit: OBAuditTrailPort,
    ) -> None:
        self._store = store
        self._registry = registry
        self._audit = audit

    async def create_consent(
        self,
        entity_id: str,
        aspsp_id: str,
        consent_type: ConsentType,
        permissions: list[AccountAccessType],
        actor: str,
        redirect_uri: str | None = None,
    ) -> Consent:
        """Create a new consent (status: AWAITING_AUTHORISATION).

        PSD2 RTS Art.10: 90-day expiry from creation.
        Raises ValueError if the ASPSP is not found.
        """
        aspsp = await self._registry.get(aspsp_id)
        if aspsp is None:
            raise ValueError(f"ASPSP not found: {aspsp_id}")

        now = datetime.now(UTC)
        consent = Consent(
            id=str(uuid.uuid4()),
            type=consent_type,
            aspsp_id=aspsp_id,
            entity_id=entity_id,
            permissions=permissions,
            status=ConsentStatus.AWAITING_AUTHORISATION,
            created_at=now,
            expires_at=now + _90_DAYS,
            redirect_uri=redirect_uri,
        )
        await self._store.save(consent)
        await self._audit.append(
            _new_event(
                event_type="consent.created",
                entity_id=entity_id,
                actor=actor,
                consent_id=consent.id,
                details={"aspsp_id": aspsp_id, "type": consent_type.value},
            )
        )
        return consent

    async def authorise_consent(
        self,
        consent_id: str,
        auth_code: str,
        actor: str,
    ) -> Consent:
        """Mark consent as AUTHORISED after successful SCA.

        Raises ValueError if not found, already authorised, or revoked/expired.
        """
        consent = await self._store.get(consent_id)
        if consent is None:
            raise ValueError(f"Consent not found: {consent_id}")

        if consent.status == ConsentStatus.AUTHORISED:
            raise ValueError(f"Consent already authorised: {consent_id}")

        if consent.status in (ConsentStatus.REVOKED, ConsentStatus.EXPIRED):
            raise ValueError(f"Consent cannot be authorised (status={consent.status.value})")

        updated = await self._store.update_status(
            consent_id,
            ConsentStatus.AUTHORISED,
            authorised_at=datetime.now(UTC),
        )
        await self._audit.append(
            _new_event(
                event_type="consent.authorised",
                entity_id=consent.entity_id,
                actor=actor,
                consent_id=consent_id,
                details={"auth_code_prefix": auth_code[:4] + "****"},
            )
        )
        return updated

    async def revoke_consent(self, consent_id: str, actor: str) -> Consent:
        """Revoke an active consent.

        Raises ValueError if not found or already revoked.
        """
        consent = await self._store.get(consent_id)
        if consent is None:
            raise ValueError(f"Consent not found: {consent_id}")

        if consent.status == ConsentStatus.REVOKED:
            raise ValueError(f"Consent already revoked: {consent_id}")

        updated = await self._store.update_status(consent_id, ConsentStatus.REVOKED)
        await self._audit.append(
            _new_event(
                event_type="consent.revoked",
                entity_id=consent.entity_id,
                actor=actor,
                consent_id=consent_id,
                details={},
            )
        )
        return updated

    async def get_consent(self, consent_id: str) -> Consent | None:
        """Retrieve a consent by ID."""
        return await self._store.get(consent_id)

    async def list_consents(self, entity_id: str) -> list[Consent]:
        """List all consents for an entity."""
        return await self._store.list_by_entity(entity_id)

    async def is_valid(self, consent_id: str) -> bool:
        """Return True iff the consent is AUTHORISED and not expired."""
        consent = await self._store.get(consent_id)
        if consent is None:
            return False
        if consent.status != ConsentStatus.AUTHORISED:
            return False
        return datetime.now(UTC) < consent.expires_at
