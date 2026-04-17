"""
tests/test_dispute_resolution/test_investigation_engine.py
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.dispute_resolution.dispute_intake import DisputeIntake
from services.dispute_resolution.investigation_engine import InvestigationEngine
from services.dispute_resolution.models import (
    DisputeStatus,
    DisputeType,
    EvidenceType,
    InMemoryDisputeStore,
    InMemoryEvidenceStore,
)


def _setup():
    dispute_store = InMemoryDisputeStore()
    evidence_store = InMemoryEvidenceStore()
    intake = DisputeIntake(dispute_store=dispute_store, evidence_store=evidence_store)
    engine = InvestigationEngine(dispute_store=dispute_store, evidence_store=evidence_store)
    return intake, engine


class TestAssignInvestigator:
    def test_returns_under_investigation(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assign_investigator(r["dispute_id"], "inv-007")
        assert result["status"] == DisputeStatus.UNDER_INVESTIGATION.value

    def test_investigator_id_in_result(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assign_investigator(r["dispute_id"], "inv-007")
        assert result["investigator_id"] == "inv-007"

    def test_unknown_dispute_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.assign_investigator("nonexistent", "inv-001")

    def test_dispute_id_in_result(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assign_investigator(r["dispute_id"], "inv-007")
        assert result["dispute_id"] == r["dispute_id"]


class TestGatherEvidence:
    def test_empty_evidence_count(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.gather_evidence(r["dispute_id"])
        assert result["evidence_count"] == 0
        assert result["evidence"] == []

    def test_counts_attached_evidence(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        intake.attach_evidence(r["dispute_id"], EvidenceType.RECEIPT, b"receipt")
        intake.attach_evidence(r["dispute_id"], EvidenceType.SCREENSHOT, b"screenshot")
        result = engine.gather_evidence(r["dispute_id"])
        assert result["evidence_count"] == 2

    def test_evidence_has_hash(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        intake.attach_evidence(r["dispute_id"], EvidenceType.PHOTO, b"photo_data")
        result = engine.gather_evidence(r["dispute_id"])
        assert len(result["evidence"][0]["file_hash"]) == 64

    def test_unknown_dispute_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.gather_evidence("nonexistent")


class TestAssessLiability:
    def test_merchant_liability(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assess_liability(r["dispute_id"], "MERCHANT")
        assert result["liable_party"] == "MERCHANT"

    def test_issuer_liability(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assess_liability(r["dispute_id"], "ISSUER")
        assert result["liable_party"] == "ISSUER"

    def test_shared_liability(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assess_liability(r["dispute_id"], "SHARED")
        assert result["liable_party"] == "SHARED"

    def test_invalid_liable_party_raises(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        with pytest.raises(ValueError, match="Invalid liable_party"):
            engine.assess_liability(r["dispute_id"], "BANK")

    def test_unknown_dispute_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.assess_liability("nonexistent", "MERCHANT")

    def test_assessment_at_in_result(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.assess_liability(r["dispute_id"], "MERCHANT")
        assert "assessment_at" in result


class TestRequestAdditionalEvidence:
    def test_status_becomes_pending_evidence(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.request_additional_evidence(r["dispute_id"])
        assert result["status"] == DisputeStatus.PENDING_EVIDENCE.value

    def test_unknown_dispute_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.request_additional_evidence("nonexistent")
