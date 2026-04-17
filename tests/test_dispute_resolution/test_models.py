"""
tests/test_dispute_resolution/test_models.py — models + stores
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.dispute_resolution.models import (
    ChargebackRecord,
    Dispute,
    DisputeEvidence,
    DisputeStatus,
    DisputeType,
    EscalationLevel,
    EscalationRecord,
    EvidenceType,
    InMemoryChargebackStore,
    InMemoryDisputeStore,
    InMemoryEscalationStore,
    InMemoryEvidenceStore,
    InMemoryResolutionStore,
    ResolutionOutcome,
    ResolutionProposal,
    compute_evidence_hash,
)

# ---------------------------------------------------------------------------
# compute_evidence_hash
# ---------------------------------------------------------------------------


class TestComputeEvidenceHash:
    def test_returns_64_char_hex(self) -> None:
        result = compute_evidence_hash(b"hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        assert compute_evidence_hash(b"data") == compute_evidence_hash(b"data")

    def test_different_inputs_produce_different_hashes(self) -> None:
        assert compute_evidence_hash(b"a") != compute_evidence_hash(b"b")

    def test_empty_bytes_returns_known_sha256(self) -> None:
        result = compute_evidence_hash(b"")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ---------------------------------------------------------------------------
# DisputeType enum
# ---------------------------------------------------------------------------


class TestDisputeType:
    def test_all_values_present(self) -> None:
        values = {e.value for e in DisputeType}
        assert "UNAUTHORIZED_TRANSACTION" in values
        assert "DUPLICATE_CHARGE" in values
        assert "MERCHANDISE_NOT_RECEIVED" in values
        assert "DEFECTIVE_MERCHANDISE" in values
        assert "CREDIT_NOT_PROCESSED" in values
        assert len(values) == 5


# ---------------------------------------------------------------------------
# DisputeStatus enum
# ---------------------------------------------------------------------------


class TestDisputeStatus:
    def test_all_statuses(self) -> None:
        values = {e.value for e in DisputeStatus}
        assert "OPENED" in values
        assert "UNDER_INVESTIGATION" in values
        assert "PENDING_EVIDENCE" in values
        assert "RESOLVED" in values
        assert "CLOSED" in values
        assert "ESCALATED" in values
        assert len(values) == 6


# ---------------------------------------------------------------------------
# EvidenceType enum
# ---------------------------------------------------------------------------


class TestEvidenceType:
    def test_all_types(self) -> None:
        values = {e.value for e in EvidenceType}
        assert "RECEIPT" in values
        assert "SCREENSHOT" in values
        assert "BANK_STATEMENT" in values
        assert "COMMUNICATION" in values
        assert "PHOTO" in values
        assert len(values) == 5


# ---------------------------------------------------------------------------
# ResolutionOutcome enum
# ---------------------------------------------------------------------------


class TestResolutionOutcome:
    def test_all_outcomes(self) -> None:
        values = {e.value for e in ResolutionOutcome}
        assert "UPHELD" in values
        assert "PARTIAL_REFUND" in values
        assert "REJECTED" in values
        assert "WITHDRAWN" in values
        assert len(values) == 4


# ---------------------------------------------------------------------------
# EscalationLevel enum
# ---------------------------------------------------------------------------


class TestEscalationLevel:
    def test_all_levels(self) -> None:
        values = {e.value for e in EscalationLevel}
        assert "LEVEL_1" in values
        assert "LEVEL_2" in values
        assert "FOS" in values
        assert len(values) == 3


# ---------------------------------------------------------------------------
# Dispute frozen dataclass
# ---------------------------------------------------------------------------


class TestDisputeDataclass:
    def _make(self, **kwargs) -> Dispute:
        defaults = dict(
            dispute_id="d-001",
            customer_id="c-001",
            payment_id="p-001",
            dispute_type=DisputeType.UNAUTHORIZED_TRANSACTION,
            status=DisputeStatus.OPENED,
            amount=Decimal("100.00"),
            description="test",
            created_at=datetime.now(UTC),
            sla_deadline=datetime.now(UTC) + timedelta(days=56),
        )
        defaults.update(kwargs)
        return Dispute(**defaults)

    def test_frozen(self) -> None:
        d = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            d.status = DisputeStatus.CLOSED  # type: ignore[misc]

    def test_replace_works(self) -> None:
        d = self._make()
        d2 = dataclasses.replace(d, status=DisputeStatus.CLOSED)
        assert d2.status == DisputeStatus.CLOSED
        assert d.status == DisputeStatus.OPENED

    def test_decimal_amount(self) -> None:
        d = self._make(amount=Decimal("9999.99"))
        assert isinstance(d.amount, Decimal)

    def test_defaults(self) -> None:
        d = self._make()
        assert d.investigator_id == ""
        assert d.liability_party == ""
        assert d.outcome is None
        assert d.resolved_at is None


# ---------------------------------------------------------------------------
# DisputeEvidence frozen dataclass
# ---------------------------------------------------------------------------


class TestDisputeEvidenceDataclass:
    def test_frozen(self) -> None:
        ev = DisputeEvidence(
            evidence_id="e-001",
            dispute_id="d-001",
            evidence_type=EvidenceType.SCREENSHOT,
            file_hash=compute_evidence_hash(b"content"),
            description="test",
            submitted_at=datetime.now(UTC),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            ev.evidence_id = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ResolutionProposal frozen dataclass
# ---------------------------------------------------------------------------


class TestResolutionProposalDataclass:
    def test_frozen(self) -> None:
        rp = ResolutionProposal(
            proposal_id="rp-001",
            dispute_id="d-001",
            outcome=ResolutionOutcome.UPHELD,
            refund_amount=Decimal("100.00"),
            reason="authorised",
            proposed_at=datetime.now(UTC),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            rp.outcome = ResolutionOutcome.REJECTED  # type: ignore[misc]

    def test_refund_amount_optional(self) -> None:
        rp = ResolutionProposal(
            proposal_id="rp-002",
            dispute_id="d-001",
            outcome=ResolutionOutcome.REJECTED,
            refund_amount=None,
            reason="invalid",
            proposed_at=datetime.now(UTC),
        )
        assert rp.refund_amount is None


# ---------------------------------------------------------------------------
# ChargebackRecord frozen dataclass
# ---------------------------------------------------------------------------


class TestChargebackRecordDataclass:
    def test_frozen(self) -> None:
        cb = ChargebackRecord(
            chargeback_id="cb-001",
            dispute_id="d-001",
            scheme="VISA",
            amount=Decimal("100.00"),
            reason_code="4853",
            initiated_at=datetime.now(UTC),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            cb.scheme = "MASTERCARD"  # type: ignore[misc]

    def test_default_status(self) -> None:
        cb = ChargebackRecord(
            chargeback_id="cb-001",
            dispute_id="d-001",
            scheme="VISA",
            amount=Decimal("50.00"),
            reason_code="4853",
            initiated_at=datetime.now(UTC),
        )
        assert cb.status == "INITIATED"


# ---------------------------------------------------------------------------
# InMemoryDisputeStore
# ---------------------------------------------------------------------------


class TestInMemoryDisputeStore:
    def _make_dispute(self, dispute_id: str = "d-001") -> Dispute:
        return Dispute(
            dispute_id=dispute_id,
            customer_id="c-001",
            payment_id="p-001",
            dispute_type=DisputeType.DUPLICATE_CHARGE,
            status=DisputeStatus.OPENED,
            amount=Decimal("50.00"),
            description="duplicate",
            created_at=datetime.now(UTC),
            sla_deadline=datetime.now(UTC) + timedelta(days=56),
        )

    def test_save_and_get(self) -> None:
        store = InMemoryDisputeStore()
        d = self._make_dispute()
        store.save(d)
        assert store.get("d-001") is d

    def test_get_missing_returns_none(self) -> None:
        store = InMemoryDisputeStore()
        assert store.get("nonexistent") is None

    def test_update(self) -> None:
        store = InMemoryDisputeStore()
        d = self._make_dispute()
        store.save(d)
        updated = dataclasses.replace(d, status=DisputeStatus.UNDER_INVESTIGATION)
        store.update(updated)
        assert store.get("d-001").status == DisputeStatus.UNDER_INVESTIGATION

    def test_list_by_customer(self) -> None:
        store = InMemoryDisputeStore()
        d1 = self._make_dispute("d-001")
        d2 = self._make_dispute("d-002")
        store.save(d1)
        store.save(d2)
        result = store.list_by_customer("c-001")
        assert len(result) == 2

    def test_list_by_customer_filters_correctly(self) -> None:
        store = InMemoryDisputeStore()
        d1 = self._make_dispute("d-001")
        d2 = Dispute(
            dispute_id="d-003",
            customer_id="c-other",
            payment_id="p-002",
            dispute_type=DisputeType.DUPLICATE_CHARGE,
            status=DisputeStatus.OPENED,
            amount=Decimal("10.00"),
            description="other",
            created_at=datetime.now(UTC),
            sla_deadline=datetime.now(UTC) + timedelta(days=56),
        )
        store.save(d1)
        store.save(d2)
        result = store.list_by_customer("c-001")
        assert len(result) == 1
        assert result[0].dispute_id == "d-001"


# ---------------------------------------------------------------------------
# InMemoryEvidenceStore (append-only I-24)
# ---------------------------------------------------------------------------


class TestInMemoryEvidenceStore:
    def _make_evidence(self, evidence_id: str = "e-001") -> DisputeEvidence:
        return DisputeEvidence(
            evidence_id=evidence_id,
            dispute_id="d-001",
            evidence_type=EvidenceType.RECEIPT,
            file_hash=compute_evidence_hash(b"file"),
            description="doc",
            submitted_at=datetime.now(UTC),
        )

    def test_save_and_list(self) -> None:
        store = InMemoryEvidenceStore()
        ev = self._make_evidence()
        store.save(ev)
        result = store.list_by_dispute("d-001")
        assert len(result) == 1

    def test_append_only_no_update_method(self) -> None:
        store = InMemoryEvidenceStore()
        assert not hasattr(store, "update")

    def test_multiple_saves_append(self) -> None:
        store = InMemoryEvidenceStore()
        store.save(self._make_evidence("e-001"))
        store.save(self._make_evidence("e-002"))
        assert len(store.list_by_dispute("d-001")) == 2

    def test_list_by_dispute_filters(self) -> None:
        store = InMemoryEvidenceStore()
        ev1 = self._make_evidence("e-001")
        ev2 = DisputeEvidence(
            evidence_id="e-002",
            dispute_id="d-other",
            evidence_type=EvidenceType.PHOTO,
            file_hash=compute_evidence_hash(b"other"),
            description="other",
            submitted_at=datetime.now(UTC),
        )
        store.save(ev1)
        store.save(ev2)
        assert len(store.list_by_dispute("d-001")) == 1


# ---------------------------------------------------------------------------
# InMemoryEscalationStore (append-only I-24)
# ---------------------------------------------------------------------------


class TestInMemoryEscalationStore:
    def test_append_only_no_update_method(self) -> None:
        store = InMemoryEscalationStore()
        assert not hasattr(store, "update")

    def test_save_and_list(self) -> None:
        store = InMemoryEscalationStore()
        esc = EscalationRecord(
            escalation_id="esc-001",
            dispute_id="d-001",
            level=EscalationLevel.LEVEL_1,
            reason="SLA breach",
            escalated_at=datetime.now(UTC),
        )
        store.save(esc)
        result = store.list_by_dispute("d-001")
        assert len(result) == 1

    def test_multiple_escalations_append(self) -> None:
        store = InMemoryEscalationStore()
        for level in [EscalationLevel.LEVEL_1, EscalationLevel.LEVEL_2]:
            store.save(
                EscalationRecord(
                    escalation_id=f"esc-{level.value}",
                    dispute_id="d-001",
                    level=level,
                    reason="test",
                    escalated_at=datetime.now(UTC),
                )
            )
        assert len(store.list_by_dispute("d-001")) == 2


# ---------------------------------------------------------------------------
# InMemoryResolutionStore
# ---------------------------------------------------------------------------


class TestInMemoryResolutionStore:
    def _make_proposal(self, proposal_id: str = "rp-001") -> ResolutionProposal:
        return ResolutionProposal(
            proposal_id=proposal_id,
            dispute_id="d-001",
            outcome=ResolutionOutcome.UPHELD,
            refund_amount=Decimal("100.00"),
            reason="valid",
            proposed_at=datetime.now(UTC),
        )

    def test_save_and_get(self) -> None:
        store = InMemoryResolutionStore()
        rp = self._make_proposal()
        store.save(rp)
        assert store.get("rp-001") is rp

    def test_get_missing_returns_none(self) -> None:
        store = InMemoryResolutionStore()
        assert store.get("missing") is None

    def test_update(self) -> None:
        store = InMemoryResolutionStore()
        rp = self._make_proposal()
        store.save(rp)
        updated = dataclasses.replace(rp, approved_by="admin")
        store.update(updated)
        assert store.get("rp-001").approved_by == "admin"


# ---------------------------------------------------------------------------
# InMemoryChargebackStore
# ---------------------------------------------------------------------------


class TestInMemoryChargebackStore:
    def _make_cb(self, cb_id: str = "cb-001") -> ChargebackRecord:
        return ChargebackRecord(
            chargeback_id=cb_id,
            dispute_id="d-001",
            scheme="VISA",
            amount=Decimal("100.00"),
            reason_code="4853",
            initiated_at=datetime.now(UTC),
        )

    def test_save_and_get(self) -> None:
        store = InMemoryChargebackStore()
        cb = self._make_cb()
        store.save(cb)
        assert store.get("cb-001") is cb

    def test_list_by_dispute(self) -> None:
        store = InMemoryChargebackStore()
        store.save(self._make_cb("cb-001"))
        store.save(self._make_cb("cb-002"))
        result = store.list_by_dispute("d-001")
        assert len(result) == 2
