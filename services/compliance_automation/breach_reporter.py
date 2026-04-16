"""
services/compliance_automation/breach_reporter.py
IL-CAE-01 | Phase 23

Breach detection and FCA reporting (SUP 15.3).
Material breaches must be reported within 1 business day.
HITL gate: FCA submissions require Compliance Officer approval (I-27).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

from services.compliance_automation.models import (
    BreachEvent,
    BreachSeverity,
    CheckStatus,
    CheckStorePort,
    ComplianceCheck,
    ReportStorePort,
)

_REPORTING_DEADLINE_HOURS = 24  # SUP 15.3: 1 business day


class BreachReporter:
    """Detects compliance breaches from check results and manages FCA reporting."""

    def __init__(
        self,
        check_store: CheckStorePort,
        report_store: ReportStorePort,
    ) -> None:
        self._check_store = check_store
        self._report_store = report_store
        self._breaches: list[BreachEvent] = []

    async def detect_breaches(
        self,
        entity_id: str,
        checks: list[ComplianceCheck],
    ) -> list[BreachEvent]:
        """Create BreachEvents for every FAIL check, classified by severity."""
        new_breaches: list[BreachEvent] = []
        for check in checks:
            if check.status != CheckStatus.FAIL:
                continue
            severity = self._classify_severity(check.rule_id)
            breach = BreachEvent(
                breach_id=str(uuid4()),
                entity_id=entity_id,
                rule_id=check.rule_id,
                severity=severity,
                description=check.finding,
                detected_at=datetime.now(UTC),
                reported_to_fca=False,
                fca_reported_at=None,
            )
            self._breaches.append(breach)
            new_breaches.append(breach)
        return new_breaches

    def _classify_severity(self, rule_id: str) -> BreachSeverity:
        """Determine breach severity from rule_id prefix."""
        if rule_id.startswith("rule-sanctions-") or rule_id.startswith("rule-aml-"):
            return BreachSeverity.MATERIAL
        if rule_id.startswith("rule-kyc-") or rule_id.startswith("rule-pep-"):
            return BreachSeverity.SIGNIFICANT
        return BreachSeverity.MINOR

    async def report_to_fca(self, breach: BreachEvent, actor: str) -> BreachEvent:
        """Mark a breach as reported to the FCA.

        Note: HITL gate enforced at agent layer (I-27). This method records
        the submission; actual FCA reporting requires human approval.
        """
        updated = dataclasses.replace(
            breach,
            reported_to_fca=True,
            fca_reported_at=datetime.now(UTC),
        )
        self._breaches = [updated if b.breach_id == breach.breach_id else b for b in self._breaches]
        return updated

    async def get_pending_breaches(
        self,
        entity_id: str | None = None,
    ) -> list[BreachEvent]:
        """Return unreported breaches, optionally filtered by entity."""
        pending = [b for b in self._breaches if not b.reported_to_fca]
        if entity_id is not None:
            pending = [b for b in pending if b.entity_id == entity_id]
        return pending
