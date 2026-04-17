"""
tests/test_dispute_resolution/test_resolution_engine.py
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.dispute_resolution.dispute_intake import DisputeIntake
from services.dispute_resolution.models import (
    DisputeStatus,
    DisputeType,
    InMemoryDisputeStore,
    InMemoryEvidenceStore,
    InMemoryResolutionStore,
    ResolutionOutcome,
)
from services.dispute_resolution.resolution_engine import ResolutionEngine


def _setup():
    dispute_store = InMemoryDisputeStore()
    resolution_store = InMemoryResolutionStore()
    intake = DisputeIntake(
        dispute_store=dispute_store,
        evidence_store=InMemoryEvidenceStore(),
    )
    engine = ResolutionEngine(dispute_store=dispute_store, resolution_store=resolution_store)
    return intake, engine


class TestProposeResolution:
    def test_always_hitl_required(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("100.00")
        )
        assert result["status"] == "HITL_REQUIRED"

    def test_proposal_id_returned(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("100.00")
        )
        assert result["proposal_id"] != ""

    def test_outcome_in_result(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.PARTIAL_REFUND, Decimal("50.00")
        )
        assert result["outcome"] == ResolutionOutcome.PARTIAL_REFUND.value

    def test_refund_amount_as_string(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("75.50")
        )
        assert result["refund_amount"] == "75.50"

    def test_no_refund_amount_is_none(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        result = engine.propose_resolution(r["dispute_id"], ResolutionOutcome.REJECTED)
        assert result["refund_amount"] is None

    def test_unknown_dispute_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.propose_resolution("nonexistent", ResolutionOutcome.REJECTED)


class TestApproveResolution:
    def test_status_approved(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        proposal = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("100.00")
        )
        approved = engine.approve_resolution(proposal["proposal_id"], "admin-001")
        assert approved["status"] == "APPROVED"

    def test_approved_by_in_result(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        proposal = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("100.00")
        )
        approved = engine.approve_resolution(proposal["proposal_id"], "manager-007")
        assert approved["approved_by"] == "manager-007"

    def test_dispute_becomes_resolved(self) -> None:
        dispute_store = InMemoryDisputeStore()
        resolution_store = InMemoryResolutionStore()
        intake = DisputeIntake(dispute_store=dispute_store, evidence_store=InMemoryEvidenceStore())
        engine = ResolutionEngine(dispute_store=dispute_store, resolution_store=resolution_store)
        r = intake.file_dispute(
            "c-1", "p-1", DisputeType.UNAUTHORIZED_TRANSACTION, Decimal("100.00")
        )
        proposal = engine.propose_resolution(
            r["dispute_id"], ResolutionOutcome.UPHELD, Decimal("100.00")
        )
        engine.approve_resolution(proposal["proposal_id"], "admin")
        detail = intake.get_dispute(r["dispute_id"])
        assert detail["status"] == DisputeStatus.RESOLVED.value

    def test_unknown_proposal_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.approve_resolution("nonexistent-proposal", "admin")


class TestExecuteRefund:
    def test_returns_refund_id(self) -> None:
        _, engine = _setup()
        result = engine.execute_refund("d-001", Decimal("50.00"))
        assert "refund_id" in result
        assert result["refund_id"] != ""

    def test_amount_as_string(self) -> None:
        _, engine = _setup()
        result = engine.execute_refund("d-001", Decimal("123.45"))
        assert result["amount"] == "123.45"

    def test_status_refund_executed(self) -> None:
        _, engine = _setup()
        result = engine.execute_refund("d-001", Decimal("50.00"))
        assert result["status"] == "REFUND_EXECUTED"

    def test_zero_amount_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="positive"):
            engine.execute_refund("d-001", Decimal("0"))

    def test_negative_amount_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="positive"):
            engine.execute_refund("d-001", Decimal("-10.00"))


class TestCloseDispute:
    def test_status_closed(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.close_dispute(r["dispute_id"])
        assert result["status"] == DisputeStatus.CLOSED.value

    def test_dispute_id_in_result(self) -> None:
        intake, engine = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = engine.close_dispute(r["dispute_id"])
        assert result["dispute_id"] == r["dispute_id"]

    def test_unknown_dispute_raises(self) -> None:
        _, engine = _setup()
        with pytest.raises(ValueError, match="not found"):
            engine.close_dispute("nonexistent")
