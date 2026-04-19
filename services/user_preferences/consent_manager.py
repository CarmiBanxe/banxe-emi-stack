"""
services/user_preferences/consent_manager.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

ConsentManager — GDPR consent lifecycle management.
I-27: Consent withdrawal is irreversible — always HITL-gated.
GDPR Art.7 (conditions for consent), Art.17 (right to erasure).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import uuid

from services.user_preferences.models import (
    AuditPort,
    ConsentPort,
    ConsentRecord,
    ConsentType,
    InMemoryAuditPort,
    InMemoryConsentPort,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class ConsentManager:
    """Manages GDPR consent records with HITL gates for irreversible actions."""

    def __init__(
        self,
        consent_port: ConsentPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._consents: ConsentPort = consent_port or InMemoryConsentPort()
        self._audit: AuditPort = audit_port or InMemoryAuditPort()

    def grant_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
        ip_address: str,
        channel: str,
    ) -> ConsentRecord:
        """Create GRANTED consent record and audit log (I-24)."""
        record = ConsentRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            consent_type=consent_type,
            status="GRANTED",
            granted_at=datetime.now(UTC),
            ip_address=ip_address,
            channel=channel,
        )
        self._consents.save(record)
        self._audit.log(
            action="grant_consent",
            resource_id=record.id,
            details={
                "user_id": user_id,
                "consent_type": consent_type.value,
                "ip_address": ip_address,
                "channel": channel,
            },
            outcome="GRANTED",
        )
        return record

    def withdraw_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> HITLProposal:
        """Consent withdrawal is irreversible — always HITL (I-27)."""
        if consent_type == ConsentType.ESSENTIAL:
            raise ValueError("ESSENTIAL consent cannot be withdrawn (GDPR legitimate interest)")
        return HITLProposal(
            action="withdraw_consent",
            resource_id=f"{user_id}:{consent_type.value}",
            requires_approval_from="DPO",
            reason=(
                f"Consent withdrawal for {consent_type.value} is irreversible "
                "under GDPR Art.7 — requires human approval (I-27)"
            ),
            autonomy_level="L4",
        )

    def confirm_withdrawal(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> ConsentRecord:
        """Called after HITL approval; create WITHDRAWN record; audit (I-24)."""
        now = datetime.now(UTC)
        record = ConsentRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            consent_type=consent_type,
            status="WITHDRAWN",
            granted_at=now,
            ip_address="system",
            channel="hitl",
            withdrawn_at=now,
        )
        self._consents.save(record)
        self._audit.log(
            action="confirm_withdrawal",
            resource_id=record.id,
            details={"user_id": user_id, "consent_type": consent_type.value},
            outcome="WITHDRAWN",
        )
        return record

    def get_consent_status(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> str:
        """Return 'GRANTED' | 'WITHDRAWN' | 'NOT_SET'."""
        record = self._consents.get_latest(user_id, consent_type)
        if record is None:
            return "NOT_SET"
        return record.status

    def list_consents(self, user_id: str) -> list[ConsentRecord]:
        """Return all consent records for user."""
        return self._consents.list_user(user_id)

    def is_essential_consent_active(self, user_id: str) -> bool:
        """ESSENTIAL consent cannot be withdrawn (GDPR legitimate interest)."""
        status = self.get_consent_status(user_id, ConsentType.ESSENTIAL)
        return status in ("GRANTED", "NOT_SET")
