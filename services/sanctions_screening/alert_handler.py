from __future__ import annotations

from datetime import UTC, datetime
import hashlib

from services.sanctions_screening.models import (
    AlertCase,
    AlertStatus,
    AlertStore,
    HITLProposal,
    HitStore,
)


class AlertHandler:
    def __init__(self, alert_store: AlertStore, hit_store: HitStore) -> None:
        self._alerts = alert_store
        self._hits = hit_store

    def create_alert(
        self,
        request_id: str,
        hit_id: str,
        assigned_to: str,
    ) -> AlertCase:
        """I-24: appends to AlertStore."""
        ts = datetime.now(UTC).isoformat()
        raw = f"{request_id}{hit_id}{ts}".encode()
        alert_id = f"alert_{hashlib.sha256(raw).hexdigest()[:8]}"
        alert = AlertCase(
            alert_id=alert_id,
            request_id=request_id,
            hit_id=hit_id,
            status=AlertStatus.OPEN,
            assigned_to=assigned_to,
            created_at=ts,
        )
        self._alerts.append(alert)  # I-24
        return alert

    def escalate_alert(
        self,
        alert_id: str,
        escalation_reason: str,
        escalated_by: str,
    ) -> HITLProposal:
        """I-27: Returns HITLProposal requiring MLRO approval."""
        alert = self._alerts.get(alert_id)
        entity_name = f"alert:{alert_id}" if alert is None else alert.hit_id
        return HITLProposal(
            action="escalate_alert",
            entity_name=entity_name,
            requires_approval_from="MLRO",
            reason=escalation_reason,
        )

    def resolve_alert(
        self,
        alert_id: str,
        is_true_positive: bool,
        resolved_by: str,
        notes: str = "",
    ) -> AlertCase:
        """I-24: creates new AlertCase with RESOLVED status (no mutation)."""
        existing = self._alerts.get(alert_id)
        if existing is None:
            raise ValueError(f"Alert {alert_id} not found")
        ts = datetime.now(UTC).isoformat()
        new_status = AlertStatus.RESOLVED_TRUE if is_true_positive else AlertStatus.RESOLVED_FALSE
        resolved = AlertCase(
            alert_id=existing.alert_id,
            request_id=existing.request_id,
            hit_id=existing.hit_id,
            status=new_status,
            assigned_to=resolved_by,
            created_at=existing.created_at,
            resolved_at=ts,
            resolution_notes=notes,
        )
        self._alerts.append(resolved)  # I-24: new record, not mutation
        return resolved

    def auto_block_confirmed(
        self,
        alert_id: str,
        entity_name: str,
    ) -> HITLProposal:
        """I-27: freeze is irreversible → ALWAYS HITLProposal."""
        return HITLProposal(
            action="auto_block_entity",
            entity_name=entity_name,
            requires_approval_from="MLRO",
            reason=f"Confirmed match: auto-block {entity_name} (alert {alert_id})",
        )

    def get_pending_alerts(self) -> list[AlertCase]:
        return self._alerts.list_open()

    def get_alert_stats(self) -> dict:
        open_alerts = self._alerts.list_by_status(AlertStatus.OPEN)
        resolved_true = self._alerts.list_by_status(AlertStatus.RESOLVED_TRUE)
        resolved_false = self._alerts.list_by_status(AlertStatus.RESOLVED_FALSE)
        escalated = self._alerts.list_by_status(AlertStatus.ESCALATED)
        total = len(open_alerts) + len(resolved_true) + len(resolved_false) + len(escalated)
        return {
            "total": total,
            "open": len(open_alerts),
            "resolved_true": len(resolved_true),
            "resolved_false": len(resolved_false),
            "escalated": len(escalated),
        }
