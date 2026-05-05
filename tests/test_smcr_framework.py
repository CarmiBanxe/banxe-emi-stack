"""
tests/test_smcr_framework.py
Tests for SMCRFramework (IL-GOV-01).

Acceptance criteria:
- test_smcr_smf_role_registered
- test_smcr_certified_person_annual_check
- test_smcr_conduct_rule_breach_reported (I-27)
- test_smcr_responsibility_map_complete
- test_smcr_audit_trail (I-24)
- test_smcr_fca_reporting_data
"""

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
    ConductRuleTier,
    SeniorManager,
    SMFRole,
)
from services.compliance_automation.smcr_registry import InMemorySMCRRegistry

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def registry():
    return InMemorySMCRRegistry()


@pytest.fixture
def audit():
    return InMemorySMCRAuditPort()


@pytest.fixture
def framework(registry, audit):
    return SMCRFramework(registry=registry, audit=audit)


# ── SMF Registration Tests ───────────────────────────────────────────────────


class TestSMFRegistration:
    def test_smcr_smf_role_registered(self, framework):
        """AC: SMF16 (Compliance) and SMF17 (MLRO) registered."""
        smf16 = framework.register_smf(
            person_id="p-001",
            name="Jane Compliance",
            role=SMFRole.SMF16,
            fca_reference="IRN-001",
            statement_of_responsibilities="SoR: Compliance Oversight",
        )
        smf17 = framework.register_smf(
            person_id="p-002",
            name="John MLRO",
            role=SMFRole.SMF17,
            fca_reference="IRN-002",
            statement_of_responsibilities="SoR: MLRO",
        )
        assert isinstance(smf16, SeniorManager)
        assert smf16.role == SMFRole.SMF16
        assert smf17.role == SMFRole.SMF17

    def test_smf_retrievable(self, framework):
        """Registered SMF retrievable by person_id."""
        framework.register_smf(
            person_id="p-001",
            name="Jane",
            role=SMFRole.SMF16,
            fca_reference="IRN-001",
            statement_of_responsibilities="SoR",
        )
        found = framework.get_smf("p-001")
        assert found is not None
        assert found.name == "Jane"

    def test_smf_not_found(self, framework):
        """Unknown person_id returns None."""
        assert framework.get_smf("nonexistent") is None

    def test_list_smfs(self, framework):
        """List all registered SMFs."""
        framework.register_smf("p-001", "A", SMFRole.SMF16, "IRN-001", "SoR-A")
        framework.register_smf("p-002", "B", SMFRole.SMF17, "IRN-002", "SoR-B")
        assert len(framework.list_smfs()) == 2

    def test_duplicate_smf_rejected(self, framework):
        """Duplicate person_id raises ValueError."""
        framework.register_smf("p-001", "A", SMFRole.SMF16, "IRN-001", "SoR")
        with pytest.raises(ValueError, match="already registered"):
            framework.register_smf("p-001", "B", SMFRole.SMF17, "IRN-002", "SoR2")

    def test_smf_immutable(self, framework):
        """SeniorManager is frozen (I-24)."""
        smf = framework.register_smf("p-001", "A", SMFRole.SMF16, "IRN-001", "SoR")
        with pytest.raises(AttributeError):
            smf.name = "Modified"  # type: ignore[misc]


# ── Responsibility Map Tests ─────────────────────────────────────────────────


class TestResponsibilityMap:
    def test_smcr_responsibility_map_complete(self, framework):
        """AC: each SMF has Statement of Responsibilities."""
        framework.register_smf("p-001", "CEO", SMFRole.SMF1, "IRN-001", "SoR: Chief Executive")
        framework.register_smf("p-002", "MLRO", SMFRole.SMF17, "IRN-002", "SoR: MLRO duties")

        resp_map = framework.get_responsibility_map()
        assert "p-001" in resp_map
        assert "p-002" in resp_map
        assert resp_map["p-001"]["statement_of_responsibilities"] == "SoR: Chief Executive"
        assert resp_map["p-002"]["role"] == "SMF17"

    def test_responsibility_map_excludes_inactive(self, framework, registry):
        """Inactive SMFs excluded from responsibility map."""
        # Register then mark inactive by creating inactive SeniorManager directly.
        from services.compliance_automation.smcr_models import SeniorManager

        inactive = SeniorManager(
            person_id="p-inactive",
            name="Gone",
            role=SMFRole.SMF3,
            fca_reference="IRN-X",
            appointed_at="2025-01-01",
            statement_of_responsibilities="SoR",
            is_active=False,
        )
        registry.register_senior_manager(inactive)

        resp_map = framework.get_responsibility_map()
        assert "p-inactive" not in resp_map


# ── Certification Tests ──────────────────────────────────────────────────────


class TestCertification:
    def test_smcr_certified_person_registered(self, framework):
        """Certified person registered with status CERTIFIED."""
        person = framework.register_certified_person(
            person_id="cp-001",
            name="Alice Certified",
            function_title="Senior Analyst",
            certified_by="p-001",
            expires_at="2027-04-28",
        )
        assert person.certification_status == CertificationStatus.CERTIFIED

    def test_smcr_certified_person_annual_check_expired(self, framework):
        """AC: expired certification → alert."""
        framework.register_certified_person(
            person_id="cp-001",
            name="Alice",
            function_title="Analyst",
            certified_by="p-001",
            expires_at="2026-01-01",  # Already expired
        )
        alerts = framework.check_certifications("2026-04-28")
        assert len(alerts) == 1
        assert isinstance(alerts[0], CertificationAlert)
        assert "expired" in alerts[0].message.lower()

    def test_smcr_certified_person_annual_check_due(self, framework):
        """Certification due today → alert."""
        framework.register_certified_person(
            person_id="cp-001",
            name="Bob",
            function_title="Analyst",
            certified_by="p-001",
            expires_at="2026-04-28",
        )
        alerts = framework.check_certifications("2026-04-28")
        assert len(alerts) == 1
        assert "due" in alerts[0].message.lower()

    def test_certification_not_due(self, framework):
        """Future certification → no alert."""
        framework.register_certified_person(
            person_id="cp-001",
            name="Carol",
            function_title="Analyst",
            certified_by="p-001",
            expires_at="2027-12-31",
        )
        alerts = framework.check_certifications("2026-04-28")
        assert len(alerts) == 0


# ── Conduct Rules Tests ──────────────────────────────────────────────────────


class TestConductRules:
    def test_individual_conduct_rules(self, framework):
        """5 Individual Conduct Rules (Tier 1)."""
        rules = framework.get_conduct_rules(ConductRuleTier.TIER_1)
        assert len(rules) == 5

    def test_senior_manager_conduct_rules(self, framework):
        """4 Senior Manager Conduct Rules (Tier 2)."""
        rules = framework.get_conduct_rules(ConductRuleTier.TIER_2)
        assert len(rules) == 4

    def test_all_conduct_rules(self, framework):
        """9 total conduct rules."""
        rules = framework.get_conduct_rules()
        assert len(rules) == 9


# ── Breach Reporting Tests ───────────────────────────────────────────────────


class TestBreachReporting:
    def test_smcr_conduct_rule_breach_minor(self, framework):
        """MINOR breach → BreachReport (no HITL)."""
        result = framework.report_breach(
            person_id="p-001",
            rule_id="ICR-1",
            severity=BreachSeverity.MINOR,
            description="Minor compliance oversight",
            reported_by="p-002",
        )
        assert isinstance(result, BreachReport)
        assert result.status == BreachStatus.OPEN

    def test_smcr_conduct_rule_breach_major_hitl(self, framework):
        """AC: MAJOR breach → BreachHITLProposal + HITL (I-27)."""
        result = framework.report_breach(
            person_id="p-001",
            rule_id="SMCR-2",
            severity=BreachSeverity.MAJOR,
            description="Failed to ensure compliance",
            reported_by="p-002",
        )
        assert isinstance(result, BreachHITLProposal)
        assert result.requires_approval_from == "COMPLIANCE_OFFICER"
        assert "MAJOR" in result.severity

    def test_smcr_conduct_rule_breach_critical_hitl(self, framework):
        """CRITICAL breach → HITL escalation."""
        result = framework.report_breach(
            person_id="p-001",
            rule_id="ICR-1",
            severity=BreachSeverity.CRITICAL,
            description="Integrity failure",
            reported_by="p-002",
        )
        assert isinstance(result, BreachHITLProposal)
        assert "FCA notification" in result.reason

    def test_list_breaches(self, framework):
        """List all breaches."""
        framework.report_breach("p-001", "ICR-1", BreachSeverity.MINOR, "desc", "p-002")
        framework.report_breach("p-001", "ICR-2", BreachSeverity.MAJOR, "desc", "p-002")
        assert len(framework.list_breaches()) == 2

    def test_hitl_proposal_immutable(self):
        """BreachHITLProposal is frozen."""
        proposal = BreachHITLProposal(
            breach_id="b-001",
            person_id="p-001",
            rule_id="ICR-1",
            severity="MAJOR",
            reason="test",
        )
        with pytest.raises(AttributeError):
            proposal.reason = "modified"  # type: ignore[misc]


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_smcr_audit_trail_smf_registration(self, framework, audit):
        """AC: SMF registration logged (I-24)."""
        framework.register_smf("p-001", "A", SMFRole.SMF16, "IRN-001", "SoR")
        assert len(audit.entries) == 1
        assert audit.entries[0].action == "REGISTER_SMF"
        assert audit.entries[0].entity_type == "SENIOR_MANAGER"

    def test_audit_trail_certification(self, framework, audit):
        """Certification registration logged."""
        framework.register_certified_person("cp-001", "Alice", "Analyst", "p-001", "2027-12-31")
        assert any(e.action == "REGISTER_CERTIFIED" for e in audit.entries)

    def test_audit_trail_breach(self, framework, audit):
        """Breach reporting logged."""
        framework.report_breach("p-001", "ICR-1", BreachSeverity.MINOR, "desc", "p-002")
        assert any(e.action == "REPORT_BREACH" for e in audit.entries)

    def test_audit_trail_fca_export(self, framework, audit):
        """FCA export logged."""
        framework.export_fca_reporting_data()
        assert any(e.action == "EXPORT_FCA_DATA" for e in audit.entries)

    def test_audit_entry_immutable(self):
        """SMCRAuditEntry is frozen (I-24)."""
        from services.compliance_automation.smcr_models import SMCRAuditEntry

        entry = SMCRAuditEntry(
            action="TEST",
            entity_type="TEST",
            entity_id="t-001",
            actor="test",
            details="test",
        )
        with pytest.raises(AttributeError):
            entry.action = "MODIFIED"  # type: ignore[misc]


# ── FCA Reporting Tests ──────────────────────────────────────────────────────


class TestFCAReporting:
    def test_smcr_fca_reporting_data(self, framework):
        """AC: export-ready data for FCA RegData."""
        framework.register_smf("p-001", "CEO", SMFRole.SMF1, "IRN-001", "SoR-CEO")
        framework.register_certified_person("cp-001", "Alice", "Analyst", "p-001", "2027-12-31")
        framework.report_breach("p-001", "ICR-1", BreachSeverity.MINOR, "desc", "p-002")

        data = framework.export_fca_reporting_data()
        assert "senior_managers" in data
        assert "certified_persons" in data
        assert "breaches" in data
        assert "exported_at" in data
        assert len(data["senior_managers"]) == 1
        assert len(data["certified_persons"]) == 1
        assert len(data["breaches"]) == 1
        assert data["senior_managers"][0]["role"] == "SMF1"

    def test_empty_export(self, framework):
        """Empty registry exports empty lists."""
        data = framework.export_fca_reporting_data()
        assert data["senior_managers"] == []
        assert data["certified_persons"] == []
        assert data["breaches"] == []
