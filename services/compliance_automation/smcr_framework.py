"""
services/compliance_automation/smcr_framework.py
SMCRFramework — FCA Senior Managers & Certification Regime (IL-GOV-01).

Manages SMF role registry, certification tracking, conduct rules enforcement,
breach reporting, and FCA reporting data export.

I-24: Immutable audit trail.
I-27: Conduct rule breaches → HITL escalation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from services.compliance_automation.smcr_models import (
    INDIVIDUAL_CONDUCT_RULES,
    SENIOR_MANAGER_CONDUCT_RULES,
    BreachReport,
    BreachSeverity,
    BreachStatus,
    CertificationStatus,
    CertifiedPerson,
    ConductRule,
    ConductRuleTier,
    SeniorManager,
    SMCRAuditEntry,
    SMFRole,
)
from services.compliance_automation.smcr_registry import InMemorySMCRRegistry, SMCRRegistryPort

# ── Audit Port ───────────────────────────────────────────────────────────────


class SMCRAuditPort(Protocol):
    """Port for recording SMCR audit entries (I-24)."""

    def record(self, entry: SMCRAuditEntry) -> None: ...


class InMemorySMCRAuditPort:
    """In-memory audit for tests."""

    def __init__(self) -> None:
        self._entries: list[SMCRAuditEntry] = []

    def record(self, entry: SMCRAuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[SMCRAuditEntry]:
        return list(self._entries)


# ── HITL Proposal ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BreachHITLProposal:
    """Conduct rule breach requires HITL escalation (I-27)."""

    breach_id: str
    person_id: str
    rule_id: str
    severity: str
    reason: str
    requires_approval_from: str = "COMPLIANCE_OFFICER"


# ── Certification Alert ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CertificationAlert:
    """Alert for certification due/expired."""

    person_id: str
    name: str
    status: str
    expires_at: str
    message: str


# ── SMCR Framework ───────────────────────────────────────────────────────────


class SMCRFramework:
    """
    FCA SMCR compliance framework.

    Manages:
    - SMF role registration and responsibility mapping
    - Annual certification tracking
    - Conduct rules enforcement
    - Breach reporting with HITL escalation (I-27)
    - FCA reporting data export

    I-24: All operations logged to audit trail.
    I-27: Breaches escalated via HITL.
    """

    def __init__(
        self,
        registry: SMCRRegistryPort | None = None,
        audit: SMCRAuditPort | None = None,
    ) -> None:
        self._registry: SMCRRegistryPort = registry or InMemorySMCRRegistry()
        self._audit: SMCRAuditPort = audit or InMemorySMCRAuditPort()

    # ── SMF Role Management ──────────────────────────────────────────────────

    def register_smf(
        self,
        person_id: str,
        name: str,
        role: SMFRole,
        fca_reference: str,
        statement_of_responsibilities: str,
    ) -> SeniorManager:
        """Register a Senior Management Function holder."""
        manager = SeniorManager(
            person_id=person_id,
            name=name,
            role=role,
            fca_reference=fca_reference,
            appointed_at=datetime.now(UTC).isoformat(),
            statement_of_responsibilities=statement_of_responsibilities,
        )
        registered = self._registry.register_senior_manager(manager)

        self._record_audit(
            action="REGISTER_SMF",
            entity_type="SENIOR_MANAGER",
            entity_id=person_id,
            actor="SYSTEM",
            details=f"role={role.value}, fca_ref={fca_reference}",
        )

        return registered

    def get_smf(self, person_id: str) -> SeniorManager | None:
        return self._registry.get_senior_manager(person_id)

    def list_smfs(self) -> list[SeniorManager]:
        return self._registry.list_senior_managers()

    def get_responsibility_map(self) -> dict[str, dict[str, str]]:
        """Return responsibility map: person_id → {role, name, SoR}."""
        managers = self._registry.list_senior_managers()
        return {
            m.person_id: {
                "role": m.role.value,
                "name": m.name,
                "statement_of_responsibilities": m.statement_of_responsibilities,
                "fca_reference": m.fca_reference,
            }
            for m in managers
            if m.is_active
        }

    # ── Certification Management ─────────────────────────────────────────────

    def register_certified_person(
        self,
        person_id: str,
        name: str,
        function_title: str,
        certified_by: str,
        expires_at: str,
    ) -> CertifiedPerson:
        """Register a certified person with annual certification."""
        person = CertifiedPerson(
            person_id=person_id,
            name=name,
            function_title=function_title,
            certification_status=CertificationStatus.CERTIFIED,
            certified_at=datetime.now(UTC).isoformat(),
            expires_at=expires_at,
            certified_by=certified_by,
        )
        registered = self._registry.register_certified_person(person)

        self._record_audit(
            action="REGISTER_CERTIFIED",
            entity_type="CERTIFIED_PERSON",
            entity_id=person_id,
            actor=certified_by,
            details=f"function={function_title}, expires={expires_at}",
        )

        return registered

    def check_certifications(self, as_of_date: str) -> list[CertificationAlert]:
        """Check for expired or due certifications. Returns alerts."""
        alerts: list[CertificationAlert] = []
        for person in self._registry.list_certified_persons():
            if person.certification_status == CertificationStatus.REVOKED:
                continue
            if person.expires_at <= as_of_date:
                alerts.append(
                    CertificationAlert(
                        person_id=person.person_id,
                        name=person.name,
                        status="EXPIRED" if person.expires_at < as_of_date else "DUE",
                        expires_at=person.expires_at,
                        message=(
                            f"Certification for {person.name} ({person.function_title}) "
                            f"{'expired' if person.expires_at < as_of_date else 'due'} "
                            f"on {person.expires_at}. Annual renewal required."
                        ),
                    )
                )

        if alerts:
            self._record_audit(
                action="CERTIFICATION_CHECK",
                entity_type="CERTIFIED_PERSON",
                entity_id="BATCH",
                actor="SYSTEM",
                details=f"alerts={len(alerts)}, as_of={as_of_date}",
            )

        return alerts

    # ── Conduct Rules ────────────────────────────────────────────────────────

    def get_conduct_rules(self, tier: ConductRuleTier | None = None) -> list[ConductRule]:
        """Return conduct rules, optionally filtered by tier."""
        all_rules = list(INDIVIDUAL_CONDUCT_RULES) + list(SENIOR_MANAGER_CONDUCT_RULES)
        if tier is not None:
            return [r for r in all_rules if r.tier == tier]
        return all_rules

    # ── Breach Reporting ─────────────────────────────────────────────────────

    def report_breach(
        self,
        person_id: str,
        rule_id: str,
        severity: BreachSeverity,
        description: str,
        reported_by: str,
    ) -> BreachReport | BreachHITLProposal:
        """
        Report a conduct rule breach.

        Returns BreachReport for MINOR breaches.
        Returns BreachHITLProposal for MAJOR/CRITICAL breaches (I-27).
        """
        breach_id = f"breach-{uuid4().hex[:8]}"
        report = BreachReport(
            breach_id=breach_id,
            person_id=person_id,
            rule_id=rule_id,
            severity=severity,
            status=BreachStatus.OPEN,
            description=description,
            reported_by=reported_by,
        )
        self._registry.file_breach(report)

        self._record_audit(
            action="REPORT_BREACH",
            entity_type="BREACH",
            entity_id=breach_id,
            actor=reported_by,
            details=f"person={person_id}, rule={rule_id}, severity={severity.value}",
        )

        # I-27: HITL escalation for MAJOR/CRITICAL.
        if severity in (BreachSeverity.MAJOR, BreachSeverity.CRITICAL):
            return BreachHITLProposal(
                breach_id=breach_id,
                person_id=person_id,
                rule_id=rule_id,
                severity=severity.value,
                reason=(
                    f"{severity.value} conduct rule breach ({rule_id}) by {person_id}. "
                    "Compliance officer review and potential FCA notification required (I-27)."
                ),
            )

        return report

    def list_breaches(self, status: str | None = None) -> list[BreachReport]:
        return self._registry.list_breaches(status)

    # ── FCA Reporting ────────────────────────────────────────────────────────

    def export_fca_reporting_data(self) -> dict:
        """Export SMCR data in FCA RegData-ready format."""
        managers = self._registry.list_senior_managers()
        certified = self._registry.list_certified_persons()
        breaches = self._registry.list_breaches()

        self._record_audit(
            action="EXPORT_FCA_DATA",
            entity_type="SMCR",
            entity_id="EXPORT",
            actor="SYSTEM",
            details=f"managers={len(managers)}, certified={len(certified)}, breaches={len(breaches)}",
        )

        return {
            "senior_managers": [
                {
                    "person_id": m.person_id,
                    "name": m.name,
                    "role": m.role.value,
                    "fca_reference": m.fca_reference,
                    "appointed_at": m.appointed_at,
                    "is_active": m.is_active,
                }
                for m in managers
            ],
            "certified_persons": [
                {
                    "person_id": p.person_id,
                    "name": p.name,
                    "function_title": p.function_title,
                    "status": p.certification_status.value,
                    "certified_at": p.certified_at,
                    "expires_at": p.expires_at,
                }
                for p in certified
            ],
            "breaches": [
                {
                    "breach_id": b.breach_id,
                    "person_id": b.person_id,
                    "rule_id": b.rule_id,
                    "severity": b.severity.value,
                    "status": b.status.value,
                }
                for b in breaches
            ],
            "exported_at": datetime.now(UTC).isoformat(),
        }

    # ── Private ──────────────────────────────────────────────────────────────

    def _record_audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        details: str,
    ) -> None:
        entry = SMCRAuditEntry(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            details=details,
        )
        self._audit.record(entry)
