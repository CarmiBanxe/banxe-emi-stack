"""
tests/test_dispute_resolution/test_dispute_intake.py
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.dispute_resolution.dispute_intake import DisputeIntake
from services.dispute_resolution.models import (
    DisputeStatus,
    DisputeType,
    EvidenceType,
    InMemoryDisputeStore,
    InMemoryEvidenceStore,
)


def _intake() -> DisputeIntake:
    store = InMemoryDisputeStore()
    evidence = InMemoryEvidenceStore()
    return DisputeIntake(dispute_store=store, evidence_store=evidence)


class TestFileDispute:
    def test_returns_dispute_id(self) -> None:
        intake = _intake()
        result = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        assert "dispute_id" in result
        assert result["dispute_id"] != ""

    def test_status_is_opened(self) -> None:
        intake = _intake()
        result = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        assert result["status"] == DisputeStatus.OPENED.value

    def test_amount_returned_as_string(self) -> None:
        intake = _intake()
        result = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("75.50"))
        assert result["amount"] == "75.50"

    def test_sla_deadline_present(self) -> None:
        intake = _intake()
        result = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        assert "sla_deadline" in result
        assert result["sla_deadline"] != ""

    def test_zero_amount_raises(self) -> None:
        intake = _intake()
        with pytest.raises(ValueError, match="positive"):
            intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("0"))

    def test_negative_amount_raises(self) -> None:
        intake = _intake()
        with pytest.raises(ValueError, match="positive"):
            intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("-10"))

    def test_dispute_type_in_result(self) -> None:
        intake = _intake()
        result = intake.file_dispute(
            "c-1", "p-1", DisputeType.MERCHANDISE_NOT_RECEIVED, Decimal("30.00")
        )
        assert result["dispute_type"] == DisputeType.MERCHANDISE_NOT_RECEIVED.value

    def test_payment_id_in_result(self) -> None:
        intake = _intake()
        result = intake.file_dispute("c-1", "p-42", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        assert result["payment_id"] == "p-42"


class TestAttachEvidence:
    def test_returns_evidence_id(self) -> None:
        intake = _intake()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        ev = intake.attach_evidence(r["dispute_id"], EvidenceType.RECEIPT, b"content")
        assert "evidence_id" in ev
        assert ev["evidence_id"] != ""

    def test_returns_sha256_hash(self) -> None:
        intake = _intake()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        ev = intake.attach_evidence(r["dispute_id"], EvidenceType.SCREENSHOT, b"image data")
        assert len(ev["file_hash"]) == 64

    def test_evidence_type_in_result(self) -> None:
        intake = _intake()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        ev = intake.attach_evidence(r["dispute_id"], EvidenceType.BANK_STATEMENT, b"stmt")
        assert ev["evidence_type"] == EvidenceType.BANK_STATEMENT.value

    def test_unknown_dispute_raises(self) -> None:
        intake = _intake()
        with pytest.raises(ValueError, match="not found"):
            intake.attach_evidence("nonexistent", EvidenceType.RECEIPT, b"data")


class TestGetDispute:
    def test_returns_dispute_details(self) -> None:
        intake = _intake()
        r = intake.file_dispute("c-1", "p-1", DisputeType.CREDIT_NOT_PROCESSED, Decimal("20.00"))
        detail = intake.get_dispute(r["dispute_id"])
        assert detail["dispute_id"] == r["dispute_id"]
        assert detail["customer_id"] == "c-1"
        assert detail["payment_id"] == "p-1"

    def test_amount_as_string(self) -> None:
        intake = _intake()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("88.88"))
        detail = intake.get_dispute(r["dispute_id"])
        assert detail["amount"] == "88.88"

    def test_unknown_dispute_raises(self) -> None:
        intake = _intake()
        with pytest.raises(ValueError, match="not found"):
            intake.get_dispute("bad-id")


class TestListDisputes:
    def test_empty_customer(self) -> None:
        intake = _intake()
        result = intake.list_disputes("c-unknown")
        assert result["count"] == 0

    def test_count_matches_filed(self) -> None:
        intake = _intake()
        intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        intake.file_dispute("c-1", "p-2", DisputeType.MERCHANDISE_NOT_RECEIVED, Decimal("100.00"))
        result = intake.list_disputes("c-1")
        assert result["count"] == 2

    def test_disputes_list_present(self) -> None:
        intake = _intake()
        intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = intake.list_disputes("c-1")
        assert len(result["disputes"]) == 1
        assert "dispute_id" in result["disputes"][0]
