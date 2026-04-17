"""
tests/test_dispute_resolution/test_escalation_manager.py
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.dispute_resolution.dispute_intake import DisputeIntake
from services.dispute_resolution.escalation_manager import EscalationManager
from services.dispute_resolution.models import (
    DisputeStatus,
    DisputeType,
    EscalationLevel,
    InMemoryDisputeStore,
    InMemoryEscalationStore,
    InMemoryEvidenceStore,
)


def _setup():
    dispute_store = InMemoryDisputeStore()
    escalation_store = InMemoryEscalationStore()
    intake = DisputeIntake(dispute_store=dispute_store, evidence_store=InMemoryEvidenceStore())
    manager = EscalationManager(dispute_store=dispute_store, escalation_store=escalation_store)
    return intake, manager, dispute_store


class TestCheckSlaBreach:
    def test_no_breach_for_new_dispute(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        assert manager.check_sla_breach(r["dispute_id"]) is False

    def test_breach_for_past_sla(self) -> None:
        intake, manager, dispute_store = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        dispute = dispute_store.get(r["dispute_id"])
        past_deadline = dataclasses.replace(
            dispute,
            sla_deadline=datetime.now(UTC) - timedelta(days=1),
        )
        dispute_store.update(past_deadline)
        assert manager.check_sla_breach(r["dispute_id"]) is True

    def test_unknown_dispute_raises(self) -> None:
        _, manager, _ = _setup()
        with pytest.raises(ValueError, match="not found"):
            manager.check_sla_breach("nonexistent")


class TestEscalateDispute:
    def test_returns_escalation_id(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.escalate_dispute(r["dispute_id"], "SLA breach")
        assert result["escalation_id"] != ""

    def test_status_becomes_escalated(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.escalate_dispute(r["dispute_id"], "unresolved")
        assert result["status"] == DisputeStatus.ESCALATED.value

    def test_default_level_is_level_1(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.escalate_dispute(r["dispute_id"], "reason")
        assert result["level"] == EscalationLevel.LEVEL_1.value

    def test_custom_level(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.escalate_dispute(r["dispute_id"], "reason", EscalationLevel.LEVEL_2)
        assert result["level"] == EscalationLevel.LEVEL_2.value

    def test_unknown_dispute_raises(self) -> None:
        _, manager, _ = _setup()
        with pytest.raises(ValueError, match="not found"):
            manager.escalate_dispute("nonexistent", "reason")


class TestEscalateToFos:
    def test_fos_level(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.escalate_to_fos(r["dispute_id"], "8-week SLA breach")
        assert result["level"] == EscalationLevel.FOS.value

    def test_fos_status_escalated(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.escalate_to_fos(r["dispute_id"], "8-week SLA breach")
        assert result["status"] == DisputeStatus.ESCALATED.value


class TestGetEscalations:
    def test_empty_escalations(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        result = manager.get_escalations(r["dispute_id"])
        assert result["count"] == 0
        assert result["escalations"] == []

    def test_count_matches(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        manager.escalate_dispute(r["dispute_id"], "first", EscalationLevel.LEVEL_1)
        manager.escalate_dispute(r["dispute_id"], "second", EscalationLevel.LEVEL_2)
        result = manager.get_escalations(r["dispute_id"])
        assert result["count"] == 2

    def test_escalation_has_level_and_reason(self) -> None:
        intake, manager, _ = _setup()
        r = intake.file_dispute("c-1", "p-1", DisputeType.DUPLICATE_CHARGE, Decimal("50.00"))
        manager.escalate_dispute(r["dispute_id"], "SLA breach", EscalationLevel.FOS)
        result = manager.get_escalations(r["dispute_id"])
        esc = result["escalations"][0]
        assert esc["level"] == EscalationLevel.FOS.value
        assert esc["reason"] == "SLA breach"
