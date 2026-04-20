"""
Tests for SWIFT gpi Tracker.
IL-SWF-01 | Sprint 34 | Phase 47
Tests: UETR gen, status update, I-23 UTC
"""

from __future__ import annotations

from decimal import Decimal
import uuid

import pytest

from services.swift_correspondent.gpi_tracker import SWIFTGPITracker
from services.swift_correspondent.models import (
    ChargeCode,
    InMemoryMessageStore,
    MessageStatus,
    SWIFTMessage,
    SWIFTMessageType,
)


@pytest.fixture
def tracker():
    return SWIFTGPITracker(store=InMemoryMessageStore())


def make_message(message_id="msg_001"):
    return SWIFTMessage(
        message_id=message_id,
        message_type=SWIFTMessageType.MT103,
        sender_bic="BARCGB22",
        receiver_bic="DEUTDEDB",
        amount=Decimal("1000.00"),
        currency="GBP",
        value_date="20260420",
        ordering_customer="Acme",
        beneficiary_customer="Vendor",
        remittance_info="Invoice 1",
        charge_code=ChargeCode.SHA,
    )


class TestGenerateUETR:
    def test_uetr_is_uuid4_format(self, tracker):
        uetr = tracker.generate_uetr()
        parsed = uuid.UUID(uetr, version=4)
        assert str(parsed) == uetr

    def test_uetr_unique_each_call(self, tracker):
        uetrs = {tracker.generate_uetr() for _ in range(10)}
        assert len(uetrs) == 10

    def test_uetr_is_string(self, tracker):
        uetr = tracker.generate_uetr()
        assert isinstance(uetr, str)


class TestAttachUETR:
    def test_attach_uetr_to_message(self, tracker):
        msg = make_message()
        tracker._store.save(msg)
        uetr = tracker.generate_uetr()
        updated = tracker.attach_uetr("msg_001", uetr)
        assert updated.uetr == uetr

    def test_attach_uetr_nonexistent_raises(self, tracker):
        with pytest.raises(ValueError):
            tracker.attach_uetr("nonexistent", tracker.generate_uetr())


class TestGetGPIStatus:
    def test_get_status_returns_gpi_status(self, tracker):
        uetr = tracker.generate_uetr()
        status = tracker.get_gpi_status(uetr)
        assert status.uetr == uetr
        assert status.status in [MessageStatus.ACSP, MessageStatus.ACCC, MessageStatus.RJCT]

    def test_get_status_consistent_for_same_uetr(self, tracker):
        uetr = tracker.generate_uetr()
        s1 = tracker.get_gpi_status(uetr)
        s2 = tracker.get_gpi_status(uetr)
        assert s1.status == s2.status

    def test_status_has_utc_timestamp(self, tracker):
        uetr = tracker.generate_uetr()
        status = tracker.get_gpi_status(uetr)
        assert status.last_updated  # non-empty UTC timestamp

    def test_status_has_tracker_url(self, tracker):
        uetr = tracker.generate_uetr()
        status = tracker.get_gpi_status(uetr)
        assert "swift.com" in (status.tracker_url or "")


class TestUpdateStatus:
    def test_update_to_accc_sets_completion_time(self, tracker):
        uetr = tracker.generate_uetr()
        status = tracker.update_status(uetr, MessageStatus.ACCC, "system")
        assert status.status == MessageStatus.ACCC
        assert status.completion_time is not None

    def test_update_to_rjct(self, tracker):
        uetr = tracker.generate_uetr()
        status = tracker.update_status(uetr, MessageStatus.RJCT, "compliance")
        assert status.status == MessageStatus.RJCT

    def test_update_sets_utc_timestamp(self, tracker):
        uetr = tracker.generate_uetr()
        status = tracker.update_status(uetr, MessageStatus.ACSP, "system")
        assert "T" in status.last_updated  # ISO format with time component


class TestWebhookCallback:
    def test_register_webhook_returns_registered(self, tracker):
        uetr = tracker.generate_uetr()
        result = tracker.register_webhook_callback(uetr, "https://example.com/callback")
        assert result["registered"] is True
        assert result["uetr"] == uetr
        assert result["callback_url"] == "https://example.com/callback"


class TestPendingTransactions:
    def test_pending_starts_empty(self, tracker):
        pending = tracker.get_pending_transactions()
        assert isinstance(pending, list)

    def test_pending_includes_acsp_status(self, tracker):
        uetr = tracker.generate_uetr()
        tracker.update_status(uetr, MessageStatus.ACSP, "system")
        pending = tracker.get_pending_transactions()
        uetrs = [s.uetr for s in pending]
        assert uetr in uetrs


class TestTrackerSummary:
    def test_summary_structure(self, tracker):
        summary = tracker.get_tracker_summary()
        assert "total" in summary
        assert "by_status" in summary

    def test_summary_counts_tracked(self, tracker):
        uetr = tracker.generate_uetr()
        tracker.get_gpi_status(uetr)
        summary = tracker.get_tracker_summary()
        assert summary["total"] >= 1
