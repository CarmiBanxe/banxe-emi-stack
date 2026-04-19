"""
services/user_preferences/data_export.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

DataExport — GDPR Art.20 data portability and Art.17 erasure requests.
I-12: SHA-256 hash for all exports.
I-27: Data erasure is irreversible — always HITL-gated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import uuid

from services.user_preferences.models import (
    AuditPort,
    ConsentPort,
    DataExportRequest,
    InMemoryAuditPort,
    InMemoryConsentPort,
    InMemoryNotificationPort,
    InMemoryPreferencePort,
    NotificationPort,
    PreferencePort,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class DataExport:
    """Handles GDPR data export and erasure requests."""

    def __init__(
        self,
        pref_port: PreferencePort | None = None,
        consent_port: ConsentPort | None = None,
        notif_port: NotificationPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._prefs: PreferencePort = pref_port or InMemoryPreferencePort()
        self._consents: ConsentPort = consent_port or InMemoryConsentPort()
        self._notifs: NotificationPort = notif_port or InMemoryNotificationPort()
        self._audit: AuditPort = audit_port or InMemoryAuditPort()
        self._requests: dict[str, DataExportRequest] = {}

    def request_export(self, user_id: str, format: str = "json") -> DataExportRequest:
        """Create PENDING export request; log to audit (I-24)."""
        request = DataExportRequest(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status="PENDING",
            format=format,
            requested_at=datetime.now(UTC),
        )
        self._requests[request.id] = request
        self._audit.log(
            action="request_export",
            resource_id=request.id,
            details={"user_id": user_id, "format": format},
            outcome="PENDING",
        )
        return request

    def generate_export(self, user_id: str) -> dict:
        """Collect preferences + consents + notifications + locale."""
        preferences = [
            {"category": p.category.value, "key": p.key, "value": p.value}
            for p in self._prefs.list_user(user_id)
        ]
        consents = [
            {
                "id": c.id,
                "consent_type": c.consent_type.value,
                "status": c.status,
                "granted_at": c.granted_at.isoformat(),
            }
            for c in self._consents.list_user(user_id)
        ]
        notifications = [
            {
                "channel": n.channel.value,
                "enabled": n.enabled,
                "frequency_cap_per_day": n.frequency_cap_per_day,
            }
            for n in self._notifs.list_user(user_id)
        ]
        return {
            "user_id": user_id,
            "preferences": preferences,
            "consents": consents,
            "notifications": notifications,
            "exported_at": datetime.now(UTC).isoformat(),
        }

    def complete_export(self, request_id: str, user_id: str) -> DataExportRequest:
        """Generate export, compute sha256 (I-12), set status=COMPLETED."""
        data = self.generate_export(user_id)
        data_str = json.dumps(data, sort_keys=True, default=str)
        export_hash = hashlib.sha256(data_str.encode()).hexdigest()
        updated = DataExportRequest(
            id=request_id,
            user_id=user_id,
            status="COMPLETED",
            format=self._requests.get(
                request_id,
                DataExportRequest(
                    id=request_id,
                    user_id=user_id,
                    status="PENDING",
                    format="json",
                    requested_at=datetime.now(UTC),
                ),
            ).format,
            requested_at=self._requests[request_id].requested_at
            if request_id in self._requests
            else datetime.now(UTC),
            export_hash=export_hash,
            completed_at=datetime.now(UTC),
        )
        self._requests[request_id] = updated
        return updated

    def request_erasure(self, user_id: str) -> HITLProposal:
        """GDPR Art.17 erasure is irreversible — always HITL (I-27)."""
        return HITLProposal(
            action="erase_user_data",
            resource_id=user_id,
            requires_approval_from="DPO",
            reason=(
                "GDPR Art.17 right to erasure: data deletion is irreversible "
                "and requires human approval (I-27)"
            ),
            autonomy_level="L4",
        )

    def get_export_status(self, request_id: str) -> DataExportRequest | None:
        """Return export request by ID."""
        return self._requests.get(request_id)

    def list_exports(self, user_id: str) -> list[DataExportRequest]:
        """Return all export requests for user."""
        return [r for r in self._requests.values() if r.user_id == user_id]
