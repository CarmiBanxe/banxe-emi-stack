"""
tests/test_smcr.py
Unit tests for the SMCR (Senior Managers & Certification Regime) framework and
registry — services/compliance_automation/smcr_framework.py + smcr_registry.py.

Covers: SMF registration/lookup, responsibility mapping, certification tracking
and expiry alerts, conduct-rule retrieval, breach reporting with HITL escalation
(I-27), FCA data export, audit-trail recording (I-24), and registry fail-closed
duplicate errors.
"""

from __future__ import annotations

import pytest

from services.compliance_automation.smcr_framework import (
    BreachHITLProposal,
    CertificationAlert,
    InMemorySMCRAuditPort,
    SMCRFramework,
)
from services.compliance_automation.smcr_models import (
    BreachReport,
    BreachSeverity,
    BreachStatus,
    CertificationStatus,
    CertifiedPerson,
    ConductRuleTier,
    SeniorManager,
    SMFRole,
)
from services.compliance_automation.smcr_registry import InMemorySMCRRegistry

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def audit() -> InMemorySMCRAuditPort:
    return InMemorySMCRAuditPort()


@pytest.fixture
def registry() -> InMemorySMCRRegistry:
    return InMemorySMCRRegistry()


@pytest.fixture
def framework(
    registry: InMemorySMCRRegistry, audit: InMemorySMCRAuditPort
) -> SMCRFramework:
    return SMCRFramework(registry=registry, audit=audit)


# ── Construction / defaults ──────────────────────────────────────────────────


def test_framework_default_wiring() -> None:
    fw = SMCRFramework()
    assert fw.list_smfs() == []
    assert fw.list_breaches() == []


# ── SMF role management ──────────────────────────────────────────────────────


def test_register_smf_returns_manager_and_audits(
    framework: SMCRFramework, audit: InMemorySMCRAuditPort
) -> None:
    manager = framework.register_smf(
        person_id="p-1",
        name="Alice CEO",
        role=SMFRole.SMF1,
        fca_reference="IRN-0001",
        statement_of_responsibilities="SoR-1",
    )
    assert isinstance(manager, SeniorManager)
    assert manager.person_id == "p-1"
    assert manager.role is SMFRole.SMF1

    assert framework.get_smf("p-1") == manager
    assert framework.list_smfs() == [manager]

    actions = [e.action for e in audit.entries]
    assert "REGISTER_SMF" in actions


def test_get_smf_missing_returns_none(framework: SMCRFramework) -> None:
    assert framework.get_smf("nope") is None


def test_register_smf_duplicate_fails_closed(framework: SMCRFramework) -> None:
    framework.register_smf(
        person_id="p-1",
        name="Alice",
        role=SMFRole.SMF1,
        fca_reference="IRN-0001",
        statement_of_responsibilities="SoR-1",
    )
    with pytest.raises(ValueError, match="already registered"):
        framework.register_smf(
            person_id="p-1",
            name="Alice Again",
            role=SMFRole.SMF3,
            fca_reference="IRN-0002",
            statement_of_responsibilities="SoR-2",
        )


def test_responsibility_map_active_only(
    registry: InMemorySMCRRegistry, framework: SMCRFramework
) -> None:
    framework.register_smf(
        person_id="active-1",
        name="Active Mgr",
        role=SMFRole.SMF16,
        fca_reference="IRN-A",
        statement_of_responsibilities="SoR-A",
    )
    # Inactive manager inserted directly at the registry level.
    registry.register_senior_manager(
        SeniorManager(
            person_id="inactive-1",
            name="Retired Mgr",
            role=SMFRole.SMF17,
            fca_reference="IRN-B",
            appointed_at="2020-01-01T00:00:00+00:00",
            statement_of_responsibilities="SoR-B",
            is_active=False,
        )
    )

    rmap = framework.get_responsibility_map()
    assert "active-1" in rmap
    assert "inactive-1" not in rmap
    assert rmap["active-1"] == {
        "role": "SMF16",
        "name": "Active Mgr",
        "statement_of_responsibilities": "SoR-A",
        "fca_reference": "IRN-A",
    }


# ── Certification management ─────────────────────────────────────────────────


def test_register_certified_person_and_audit(
    framework: SMCRFramework, audit: InMemorySMCRAuditPort
) -> None:
    person = framework.register_certified_person(
        person_id="c-1",
        name="Bob Trader",
        function_title="Head of Trading",
        certified_by="p-1",
        expires_at="2027-01-01",
    )
    assert isinstance(person, CertifiedPerson)
    assert person.certification_status is CertificationStatus.CERTIFIED
    assert person.certified_by == "p-1"
    assert "REGISTER_CERTIFIED" in [e.action for e in audit.entries]


def test_register_certified_person_duplicate_fails_closed(
    framework: SMCRFramework,
) -> None:
    framework.register_certified_person(
        person_id="c-1",
        name="Bob",
        function_title="Head of Trading",
        certified_by="p-1",
        expires_at="2027-01-01",
    )
    with pytest.raises(ValueError, match="already registered"):
        framework.register_certified_person(
            person_id="c-1",
            name="Bob Dup",
            function_title="Head of Trading",
            certified_by="p-1",
            expires_at="2028-01-01",
        )


def test_check_certifications_expired_and_due(
    framework: SMCRFramework, audit: InMemorySMCRAuditPort
) -> None:
    framework.register_certified_person(
        person_id="exp-1",
        name="Expired Person",
        function_title="Risk",
        certified_by="p-1",
        expires_at="2025-01-01",
    )
    framework.register_certified_person(
        person_id="due-1",
        name="Due Person",
        function_title="Risk",
        certified_by="p-1",
        expires_at="2026-06-15",
    )
    framework.register_certified_person(
        person_id="future-1",
        name="Future Person",
        function_title="Risk",
        certified_by="p-1",
        expires_at="2099-01-01",
    )

    alerts = framework.check_certifications(as_of_date="2026-06-15")
    by_id = {a.person_id: a for a in alerts}

    assert set(by_id) == {"exp-1", "due-1"}
    assert isinstance(by_id["exp-1"], CertificationAlert)
    assert by_id["exp-1"].status == "EXPIRED"
    assert "expired" in by_id["exp-1"].message
    # expires_at == as_of_date → DUE (not strictly less than).
    assert by_id["due-1"].status == "DUE"
    assert "due" in by_id["due-1"].message

    assert "CERTIFICATION_CHECK" in [e.action for e in audit.entries]


def test_check_certifications_skips_revoked(
    registry: InMemorySMCRRegistry, framework: SMCRFramework
) -> None:
    registry.register_certified_person(
        CertifiedPerson(
            person_id="rev-1",
            name="Revoked Person",
            function_title="Risk",
            certification_status=CertificationStatus.REVOKED,
            certified_at="2024-01-01",
            expires_at="2024-06-01",
            certified_by="p-1",
        )
    )
    alerts = framework.check_certifications(as_of_date="2026-06-15")
    assert alerts == []


def test_check_certifications_no_alerts_no_audit(
    framework: SMCRFramework, audit: InMemorySMCRAuditPort
) -> None:
    framework.register_certified_person(
        person_id="ok-1",
        name="OK Person",
        function_title="Risk",
        certified_by="p-1",
        expires_at="2099-01-01",
    )
    audit_before = len(audit.entries)
    alerts = framework.check_certifications(as_of_date="2026-06-15")
    assert alerts == []
    # No CERTIFICATION_CHECK entry recorded when there are zero alerts.
    assert len(audit.entries) == audit_before


# ── Conduct rules ────────────────────────────────────────────────────────────


def test_get_conduct_rules_all(framework: SMCRFramework) -> None:
    rules = framework.get_conduct_rules()
    assert len(rules) == 9  # 5 individual + 4 senior-manager
    tiers = {r.tier for r in rules}
    assert tiers == {ConductRuleTier.TIER_1, ConductRuleTier.TIER_2}


def test_get_conduct_rules_filtered_tier1(framework: SMCRFramework) -> None:
    rules = framework.get_conduct_rules(tier=ConductRuleTier.TIER_1)
    assert len(rules) == 5
    assert all(r.tier is ConductRuleTier.TIER_1 for r in rules)


def test_get_conduct_rules_filtered_tier2(framework: SMCRFramework) -> None:
    rules = framework.get_conduct_rules(tier=ConductRuleTier.TIER_2)
    assert len(rules) == 4
    assert all(r.tier is ConductRuleTier.TIER_2 for r in rules)


# ── Breach reporting ─────────────────────────────────────────────────────────


def test_report_minor_breach_returns_report(
    framework: SMCRFramework, audit: InMemorySMCRAuditPort
) -> None:
    result = framework.report_breach(
        person_id="p-1",
        rule_id="ICR-1",
        severity=BreachSeverity.MINOR,
        description="Late disclosure",
        reported_by="mlro",
    )
    assert isinstance(result, BreachReport)
    assert result.severity is BreachSeverity.MINOR
    assert result.status is BreachStatus.OPEN
    assert result.breach_id.startswith("breach-")
    assert "REPORT_BREACH" in [e.action for e in audit.entries]

    # Breach persisted to the registry.
    assert framework.list_breaches() == [result]


@pytest.mark.parametrize("severity", [BreachSeverity.MAJOR, BreachSeverity.CRITICAL])
def test_report_serious_breach_escalates_hitl(
    framework: SMCRFramework, severity: BreachSeverity
) -> None:
    result = framework.report_breach(
        person_id="p-9",
        rule_id="SMCR-2",
        severity=severity,
        description="Systemic compliance failure",
        reported_by="mlro",
    )
    assert isinstance(result, BreachHITLProposal)
    assert result.severity == severity.value
    assert result.requires_approval_from == "COMPLIANCE_OFFICER"
    assert "I-27" in result.reason

    # HITL escalation still persists the underlying breach record.
    stored = framework.list_breaches()
    assert len(stored) == 1
    assert stored[0].breach_id == result.breach_id


def test_list_breaches_status_filter(framework: SMCRFramework) -> None:
    framework.report_breach(
        person_id="p-1",
        rule_id="ICR-1",
        severity=BreachSeverity.MINOR,
        description="d1",
        reported_by="mlro",
    )
    assert len(framework.list_breaches(status="OPEN")) == 1
    assert framework.list_breaches(status="CLOSED") == []


# ── FCA reporting ────────────────────────────────────────────────────────────


def test_export_fca_reporting_data(
    framework: SMCRFramework, audit: InMemorySMCRAuditPort
) -> None:
    framework.register_smf(
        person_id="p-1",
        name="Alice",
        role=SMFRole.SMF1,
        fca_reference="IRN-1",
        statement_of_responsibilities="SoR-1",
    )
    framework.register_certified_person(
        person_id="c-1",
        name="Bob",
        function_title="Head of Trading",
        certified_by="p-1",
        expires_at="2027-01-01",
    )
    framework.report_breach(
        person_id="p-1",
        rule_id="ICR-1",
        severity=BreachSeverity.MINOR,
        description="d",
        reported_by="mlro",
    )

    data = framework.export_fca_reporting_data()

    assert [m["person_id"] for m in data["senior_managers"]] == ["p-1"]
    assert data["senior_managers"][0]["role"] == "SMF1"
    assert data["senior_managers"][0]["is_active"] is True

    assert [p["person_id"] for p in data["certified_persons"]] == ["c-1"]
    assert data["certified_persons"][0]["status"] == "CERTIFIED"

    assert len(data["breaches"]) == 1
    assert data["breaches"][0]["severity"] == "MINOR"
    assert data["breaches"][0]["status"] == "OPEN"

    assert "exported_at" in data
    assert "EXPORT_FCA_DATA" in [e.action for e in audit.entries]


def test_export_empty_state(framework: SMCRFramework) -> None:
    data = framework.export_fca_reporting_data()
    assert data["senior_managers"] == []
    assert data["certified_persons"] == []
    assert data["breaches"] == []


# ── Audit trail (I-24) ───────────────────────────────────────────────────────


def test_audit_entries_property_is_copy(audit: InMemorySMCRAuditPort) -> None:
    snapshot = audit.entries
    snapshot.append("junk")  # type: ignore[arg-type]
    assert audit.entries == []  # internal list unaffected


# ── Registry direct coverage ─────────────────────────────────────────────────


def test_registry_get_certified_and_list(registry: InMemorySMCRRegistry) -> None:
    person = CertifiedPerson(
        person_id="c-1",
        name="Bob",
        function_title="Risk",
        certification_status=CertificationStatus.CERTIFIED,
        certified_at="2026-01-01",
        expires_at="2027-01-01",
        certified_by="p-1",
    )
    registry.register_certified_person(person)
    assert registry.get_certified_person("c-1") == person
    assert registry.get_certified_person("missing") is None
    assert registry.list_certified_persons() == [person]


def test_registry_get_senior_manager_missing(registry: InMemorySMCRRegistry) -> None:
    assert registry.get_senior_manager("missing") is None


def test_registry_file_and_list_breaches(registry: InMemorySMCRRegistry) -> None:
    report = BreachReport(
        breach_id="breach-1",
        person_id="p-1",
        rule_id="ICR-1",
        severity=BreachSeverity.MINOR,
        status=BreachStatus.OPEN,
        description="d",
        reported_by="mlro",
    )
    assert registry.file_breach(report) == report
    assert registry.list_breaches() == [report]
    assert registry.list_breaches(status="OPEN") == [report]
    assert registry.list_breaches(status="RESOLVED") == []
