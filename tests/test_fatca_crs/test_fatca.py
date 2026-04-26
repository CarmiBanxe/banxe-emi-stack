"""Tests for FATCA/CRS Self-Certification (IL-FAT-01)."""

from __future__ import annotations

from datetime import datetime

import pytest

from services.fatca_crs.fatca_models import (
    CertificationStatus,
    CRSClassification,
    TaxResidency,
)
from services.fatca_crs.self_cert_engine import (
    BLOCKED_JURISDICTIONS,
    CERT_TTL_DAYS,
    InMemoryCertStore,
    SelfCertEngine,
)


def _make_residency(country: str = "GB", tin: str = "1234567890") -> TaxResidency:
    return TaxResidency(country=country, tin=tin)


class TestTaxResidency:
    def test_masked_tin_hides_all_but_last4(self):
        res = _make_residency(tin="ABCDE12345")
        assert res.masked_tin() == "****2345"

    def test_masked_tin_short(self):
        res = _make_residency(tin="AB")
        assert res.masked_tin() == "****"

    def test_tin_not_logged_raw(self):
        res = _make_residency(tin="SECRET1234")
        assert "SECRET1234" not in res.masked_tin()


class TestSelfCertEngine:
    def test_create_cert_returns_certification(self):
        engine = SelfCertEngine()
        res = _make_residency()
        cert = engine.create_cert("CUST001", [res], us_person=False)
        assert cert.cert_id is not None
        assert cert.customer_id == "CUST001"

    def test_create_cert_status_active(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency()], us_person=False)
        assert cert.status == CertificationStatus.ACTIVE

    def test_create_cert_has_expiry(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency()], us_person=False)
        assert cert.expires_at is not None
        expires = datetime.fromisoformat(cert.expires_at)
        created = datetime.fromisoformat(cert.created_at)
        diff_days = (expires - created).days
        assert diff_days == CERT_TTL_DAYS

    def test_create_cert_blocked_jurisdiction_ru(self):
        """I-02: Russian tax residency rejected."""
        engine = SelfCertEngine()
        res = _make_residency(country="RU")
        with pytest.raises(ValueError, match="I-02"):
            engine.create_cert("CUST001", [res], us_person=False)

    def test_create_cert_blocked_jurisdiction_ir(self):
        engine = SelfCertEngine()
        with pytest.raises(ValueError):
            engine.create_cert("CUST001", [_make_residency("IR")], us_person=False)

    def test_create_cert_blocked_jurisdiction_kp(self):
        engine = SelfCertEngine()
        with pytest.raises(ValueError):
            engine.create_cert("CUST001", [_make_residency("KP")], us_person=False)

    def test_create_cert_allowed_gb(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency("GB")], us_person=False)
        assert cert.cert_id is not None

    def test_create_cert_us_person_true(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency("US")], us_person=True)
        assert cert.us_person is True

    def test_audit_log_append_only(self):
        """I-24: audit log grows with each cert created."""
        engine = SelfCertEngine()
        engine.create_cert("CUST001", [_make_residency()], us_person=False)
        engine.create_cert("CUST002", [_make_residency()], us_person=False)
        assert len(engine.audit_log) == 2

    def test_audit_log_no_raw_tin(self):
        """TIN must not appear in audit log."""
        engine = SelfCertEngine()
        engine.create_cert("CUST001", [_make_residency(tin="SECRETTIN99")], us_person=False)
        log_str = str(engine.audit_log)
        assert "SECRETTIN99" not in log_str

    def test_validate_cert_valid(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency()], us_person=False)
        result = engine.validate_cert(cert.cert_id)
        assert result.valid is True
        assert result.errors == []

    def test_validate_cert_not_found(self):
        engine = SelfCertEngine()
        result = engine.validate_cert("NONEXISTENT")
        assert result.valid is False
        assert len(result.errors) > 0

    def test_crs_classification_individual_default(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency()], us_person=False)
        assert cert.crs_classification == CRSClassification.INDIVIDUAL

    def test_crs_classification_active_nfe(self):
        engine = SelfCertEngine()
        cert = engine.create_cert(
            "CORP001",
            [_make_residency()],
            us_person=False,
            crs_classification=CRSClassification.ACTIVE_NFE,
        )
        assert cert.crs_classification == CRSClassification.ACTIVE_NFE

    def test_get_by_customer_returns_certs(self):
        store = InMemoryCertStore()
        engine = SelfCertEngine(store)
        engine.create_cert("CUST001", [_make_residency()], us_person=False)
        certs = store.get_by_customer("CUST001")
        assert len(certs) == 1

    def test_get_by_customer_empty_for_unknown(self):
        engine = SelfCertEngine()
        certs = engine._store.get_by_customer("UNKNOWN")
        assert certs == []

    def test_blocked_jurisdictions_set(self):
        assert "RU" in BLOCKED_JURISDICTIONS
        assert "IR" in BLOCKED_JURISDICTIONS
        assert "GB" not in BLOCKED_JURISDICTIONS
        assert "US" not in BLOCKED_JURISDICTIONS

    def test_multiple_residencies_one_blocked_raises(self):
        engine = SelfCertEngine()
        residencies = [_make_residency("GB"), _make_residency("RU")]
        with pytest.raises(ValueError, match="I-02"):
            engine.create_cert("CUST001", residencies, us_person=False)

    def test_multiple_residencies_all_allowed(self):
        engine = SelfCertEngine()
        residencies = [_make_residency("GB"), _make_residency("DE")]
        cert = engine.create_cert("CUST001", residencies, us_person=False)
        assert cert.cert_id is not None

    def test_cert_id_deterministic_format(self):
        engine = SelfCertEngine()
        cert = engine.create_cert("CUST001", [_make_residency()], us_person=False)
        assert cert.cert_id.startswith("cert_")


class TestFATCAAgent:
    def test_propose_us_person_change_returns_proposal(self):
        from services.fatca_crs.fatca_agent import FATCAAgent

        agent = FATCAAgent()
        proposal = agent.propose_us_person_change("cert_001", True)
        assert proposal.cert_id == "cert_001"
        assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"

    def test_propose_us_person_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.fatca_crs.fatca_agent import FATCAAgent

        agent = FATCAAgent()
        proposal = agent.propose_us_person_change("cert_001", True)
        assert proposal.approved is False

    def test_propose_crs_override_requires_mlro(self):
        """I-27: CRS override requires MLRO."""
        from services.fatca_crs.fatca_agent import FATCAAgent

        agent = FATCAAgent()
        proposal = agent.propose_crs_override("cert_001", CRSClassification.ACTIVE_NFE)
        assert proposal.requires_approval_from == "MLRO"

    def test_proposals_append(self):
        from services.fatca_crs.fatca_agent import FATCAAgent

        agent = FATCAAgent()
        agent.propose_us_person_change("cert_001", True)
        agent.propose_us_person_change("cert_002", False)
        assert len(agent.proposals) == 2

    def test_crs_classifications_enum_values(self):
        assert CRSClassification.ACTIVE_NFE == "Active_NFE"
        assert CRSClassification.PASSIVE_NFE == "Passive_NFE"
        assert CRSClassification.INDIVIDUAL == "Individual"
