from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from services.sanctions_screening.models import (
    AlertStore,
    HITLProposal,
    ScreeningStore,
)


class ComplianceReporter:
    def __init__(
        self,
        screening_store: ScreeningStore,
        alert_store: AlertStore,
    ) -> None:
        self._screening = screening_store
        self._alerts = alert_store

    def generate_sar(
        self,
        request_id: str,
        mlro_ref: str,
        actor: str,
    ) -> HITLProposal:
        """I-27: POCA 2002 s.330 — ALWAYS HITL."""
        return HITLProposal(
            action="sar_filing",
            entity_name=request_id,
            requires_approval_from="MLRO",
            reason="POCA 2002 s.330 SAR Filing",
        )

    def generate_ofsi_report(self, alert_id: str) -> dict:
        alert = self._alerts.get(alert_id)
        ts = datetime.now(UTC).isoformat()
        return {
            "ofsi_report_format": "v2026",
            "alert_id": alert_id,
            "status": alert.status if alert else "unknown",
            "generated_at": ts,
            "regulatory_ref": "OFSI",
        }

    def get_screening_stats(self, period: str = "daily") -> dict:
        # Stub: counts from in-memory stores
        ts = datetime.now(UTC).isoformat()
        return {
            "period": period,
            "generated_at": ts,
            "total": 0,
            "clear": 0,
            "possible_match": 0,
            "confirmed_match": 0,
            "error": 0,
        }

    def export_audit_trail(self, entity_name: str) -> dict:
        """I-12: SHA-256 checksum of export data."""
        ts = datetime.now(UTC).isoformat()
        data = {
            "entity_name": entity_name,
            "exported_at": ts,
            "requests": [],
            "reports": [],
            "alerts": [],
        }
        serialised = json.dumps(data, sort_keys=True).encode()
        checksum = hashlib.sha256(serialised).hexdigest()  # I-12
        return {**data, "checksum": checksum}

    def generate_board_summary(self, period: str) -> HITLProposal:
        """I-27: board report must be HITL-approved."""
        return HITLProposal(
            action="board_summary",
            entity_name="board",
            requires_approval_from="MLRO",
            reason=f"Board summary for period {period} requires MLRO approval (I-27)",
        )
