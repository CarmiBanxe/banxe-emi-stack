"""
Tests for SWIFT Message Builder.
IL-SWF-01 | Sprint 34 | Phase 47
Tests: MT103/MT202, BIC validation, remittance 140 chars, FATF EDD prefix (I-03)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.swift_correspondent.message_builder import (
    SWIFTMessageBuilder,
)
from services.swift_correspondent.models import (
    ChargeCode,
    InMemoryMessageStore,
    MessageStatus,
    SWIFTMessageType,
)


@pytest.fixture
def builder():
    return SWIFTMessageBuilder(store=InMemoryMessageStore())


class TestBuildMT103:
    def test_build_mt103_basic(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("1000.00"),
            currency="GBP",
            ordering_customer="Acme Ltd",
            beneficiary_customer="Vendor GmbH",
            remittance_info="Invoice 123",
        )
        assert msg.message_type == SWIFTMessageType.MT103
        assert msg.amount == Decimal("1000.00")
        assert msg.status == MessageStatus.DRAFT

    def test_mt103_message_id_format(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="CHASUS33",
            amount=Decimal("500"),
            currency="USD",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="ref",
        )
        assert msg.message_id.startswith("msg_")
        assert len(msg.message_id) == 12  # msg_ + 8 chars

    def test_mt103_charge_code_sha_default(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
        )
        assert msg.charge_code == ChargeCode.SHA

    def test_mt103_charge_code_ben(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
            charge_code=ChargeCode.BEN,
        )
        assert msg.charge_code == ChargeCode.BEN

    def test_mt103_sender_bic_uppercase(self, builder):
        msg = builder.build_mt103(
            sender_bic="barcgb22",
            receiver_bic="deutdedb",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
        )
        assert msg.sender_bic == "BARCGB22"
        assert msg.receiver_bic == "DEUTDEDB"

    def test_mt103_value_date_yyyymmdd(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
        )
        assert len(msg.value_date) == 8
        assert msg.value_date.isdigit()

    def test_mt103_stored_in_store(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
        )
        retrieved = builder.get_message(msg.message_id)
        assert retrieved is not None
        assert retrieved.message_id == msg.message_id

    def test_mt103_fatf_country_adds_edd_prefix(self, builder):
        # AE is in FATF greylist — BIC chars 5-6 = AE
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="ADCBAEAA",  # AE country
            amount=Decimal("100"),
            currency="AED",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="Invoice",
        )
        assert msg.remittance_info.startswith("[EDD]")

    def test_mt103_non_fatf_no_edd_prefix(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",  # DE country — not FATF
            amount=Decimal("100"),
            currency="EUR",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="Invoice",
        )
        assert not msg.remittance_info.startswith("[EDD]")

    def test_mt103_blocked_jurisdiction_raises(self, builder):
        with pytest.raises(ValueError, match="blocked"):
            builder.build_mt103(
                sender_bic="BARCGB22",
                receiver_bic="SBERRU22",  # RU country — blocked
                amount=Decimal("100"),
                currency="RUB",
                ordering_customer="A",
                beneficiary_customer="B",
                remittance_info="test",
            )


class TestBuildMT202:
    def test_build_mt202_basic(self, builder):
        msg = builder.build_mt202(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("50000.00"),
            currency="EUR",
            ordering_institution="Barclays",
            beneficiary_institution="Deutsche Bank",
        )
        assert msg.message_type == SWIFTMessageType.MT202
        assert msg.amount == Decimal("50000.00")

    def test_mt202_message_id_unique(self, builder):
        msg1 = builder.build_mt202("BARCGB22", "DEUTDEDB", Decimal("1000"), "EUR", "A", "B")
        msg2 = builder.build_mt202("BARCGB22", "CHASUS33", Decimal("2000"), "USD", "A", "B")
        assert msg1.message_id != msg2.message_id

    def test_mt202_charge_code_our(self, builder):
        msg = builder.build_mt202("BARCGB22", "DEUTDEDB", Decimal("1000"), "EUR", "A", "B")
        assert msg.charge_code == ChargeCode.OUR

    def test_mt202_amount_is_decimal(self, builder):
        msg = builder.build_mt202("BARCGB22", "DEUTDEDB", Decimal("99999.99"), "EUR", "A", "B")
        assert isinstance(msg.amount, Decimal)


class TestValidateMessage:
    def test_valid_message_returns_true(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
        )
        valid, errors = builder.validate_message(msg.message_id)
        assert valid is True
        assert errors == []

    def test_nonexistent_message_invalid(self, builder):
        valid, errors = builder.validate_message("nonexistent")
        assert valid is False
        assert len(errors) > 0

    def test_validation_updates_status(self, builder):
        msg = builder.build_mt103(
            sender_bic="BARCGB22",
            receiver_bic="DEUTDEDB",
            amount=Decimal("100"),
            currency="GBP",
            ordering_customer="A",
            beneficiary_customer="B",
            remittance_info="test",
        )
        valid, _ = builder.validate_message(msg.message_id)
        assert valid is True
        updated = builder.get_message(msg.message_id)
        assert updated.status == MessageStatus.VALIDATED


class TestCancelMessage:
    def test_cancel_returns_hitl_proposal(self, builder):
        from services.swift_correspondent.models import HITLProposal

        proposal = builder.cancel_message("msg_001", "Test cancel", "treasury_ops")
        assert isinstance(proposal, HITLProposal)
        assert proposal.action == "CANCEL_MESSAGE"
        assert proposal.autonomy_level == "L4"
        assert proposal.requires_approval_from == "TREASURY_OPS"

    def test_cancel_always_hitl_regardless_of_status(self, builder):
        proposal = builder.cancel_message("msg_001", "Urgent", "operator")
        assert proposal.autonomy_level == "L4"


class TestListMessages:
    def test_list_messages_empty(self, builder):
        msgs = builder.list_messages()
        assert isinstance(msgs, list)

    def test_list_messages_by_status(self, builder):
        builder.build_mt103("BARCGB22", "DEUTDEDB", Decimal("100"), "GBP", "A", "B", "ref")
        drafts = builder.list_messages(status=MessageStatus.DRAFT)
        assert len(drafts) >= 1

    def test_get_message_none_if_not_found(self, builder):
        assert builder.get_message("does_not_exist") is None
