"""
services/audit/audit_query.py — AuditQueryService
IL-PGA-01 | Phase 51A | Sprint 36
L2 auto: query/stats/health | L4 HITL: export (COMPLIANCE_OFFICER)
Invariants: I-24 (append-only), I-27 (HITL proposal)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import uuid

from services.audit.pgaudit_config import (
    PGAUDIT_DATABASES,
    PGAUDIT_SETTINGS,
    PGAUDIT_VERSION,
    AuditEntry,
    AuditLogPort,
    AuditStats,
)


@dataclass(frozen=True)
class HITLProposal:
    """HITL gate — AI proposes, human decides (I-27)."""

    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class AuditQueryService:
    """
    Read-only query surface over pgAudit logs.
    All writes go through the DB/port directly; this service only queries.
    """

    def __init__(self, port: AuditLogPort) -> None:
        self._port = port

    def _validate_db(self, db_name: str) -> None:
        if db_name not in PGAUDIT_DATABASES:
            raise ValueError(f"Unknown database: {db_name!r}. Must be one of {PGAUDIT_DATABASES}")

    def query_audit_log(
        self,
        db_name: str,
        table_name: str | None,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """L2 auto — query audit log entries."""
        self._validate_db(db_name)
        return self._port.query(db_name, table_name, start_date, end_date, limit)

    def get_stats(self, db_name: str) -> AuditStats:
        """L2 auto — get stats for a specific database."""
        self._validate_db(db_name)
        return self._port.get_stats(db_name)

    def get_all_stats(self) -> list[AuditStats]:
        """L2 auto — get stats for all databases."""
        return [self._port.get_stats(db) for db in PGAUDIT_DATABASES]

    def export_audit_report(
        self,
        db_name: str,
        start_date: str,
        end_date: str,
        requested_by: str,
    ) -> HITLProposal:
        """
        L4 HITL — propose an audit export. Never auto-executes (I-27).
        Returns HITLProposal; COMPLIANCE_OFFICER must approve.
        """
        self._validate_db(db_name)
        entity_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        return HITLProposal(
            action="export_audit_report",
            entity_id=entity_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=f"Audit export requested for {db_name} [{start_date} → {end_date}] by {requested_by}",
            autonomy_level="L4",
        )

    def health_check(self) -> dict:
        """L1 auto — return pgAudit health status."""
        return {
            "status": "ok",
            "databases": PGAUDIT_DATABASES,
            "pgaudit_version": PGAUDIT_VERSION,
            "settings": PGAUDIT_SETTINGS,
            "checked_at": datetime.now(UTC).isoformat(),
        }
