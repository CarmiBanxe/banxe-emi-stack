"""
Tests for SWIFT Correspondent Banking models.
IL-SWF-01 | Sprint 34 | Phase 47
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import ValidationError
import pytest

from services.swift_correspondent.models import (
    ChargeCode,
    CorrespondentBank,
    CorrespondentType,
    HITLProposal,
    InMemoryCorrespondentStore,
    InMemoryMessageStore,
    InMemoryNostroStore,
    MessageStatus,
    NostroPosition,
    SWIFTMessage,
    SWIFTMessageType,
)


def make_message(**kwargs):
    defaults = dict(
        message_id="msg_001",
        message_type=SWIFTMessageType.MT103,
        sender_bic="BARCGB22",
        receiver_bic="DEUTDEDB",
        amount=Decimal("1000.00"),
        currency="GBP",
        value_date="20260420",
        ordering_customer="Acme Ltd",
        beneficiary_customer="Vendor GmbH",
        remittance_info="Invoice 123",
        charge_code=ChargeCode.SHA,
    )
    defaults.update(kwargs)
    return SWIFTMessage(**defaults)


class TestSWIFTMessage:
    def test_valid_message_creation(self):
        msg = make_message()
        assert msg.message_id == "msg_001"
        assert msg.amount == Decimal("1000.00")
        assert msg.status == MessageStatus.DRAFT

    def test_bic_uppercase_normalised(self):
        msg = make_message(sender_bic="barcgb22", receiver_bic="deutdedb")
        assert msg.sender_bic == "BARCGB22"
        assert msg.receiver_bic == "DEUTDEDB"

    def test_bic_8_chars_valid(self):
        msg = make_message(sender_bic="BARCGB22")
        assert len(msg.sender_bic) == 8

    def test_bic_11_chars_valid(self):
        msg = make_message(sender_bic="BARCGB22XXX")
        assert len(msg.sender_bic) == 11

    def test_bic_invalid_length_raises(self):
        with pytest.raises(ValidationError):
            make_message(sender_bic="BARC")

    def test_remittance_140_chars_valid(self):
        msg = make_message(remittance_info="A" * 140)
        assert len(msg.remittance_info) == 140

    def test_remittance_over_140_raises(self):
        with pytest.raises(ValidationError):
            make_message(remittance_info="A" * 141)

    def test_amount_is_decimal(self):
        msg = make_message(amount=Decimal("9999.99"))
        assert isinstance(msg.amount, Decimal)

    def test_uetr_none_by_default(self):
        msg = make_message()
        assert msg.uetr is None

    def test_uetr_can_be_set(self):
        msg = make_message(uetr="550e8400-e29b-41d4-a716-446655440000")
        assert msg.uetr == "550e8400-e29b-41d4-a716-446655440000"

    def test_status_default_draft(self):
        msg = make_message()
        assert msg.status == MessageStatus.DRAFT

    def test_charge_codes(self):
        for code in [ChargeCode.SHA, ChargeCode.BEN, ChargeCode.OUR]:
            msg = make_message(charge_code=code)
            assert msg.charge_code == code

    def test_message_type_mt103(self):
        msg = make_message(message_type=SWIFTMessageType.MT103)
        assert msg.message_type == SWIFTMessageType.MT103

    def test_message_type_mt202(self):
        msg = make_message(message_type=SWIFTMessageType.MT202)
        assert msg.message_type == SWIFTMessageType.MT202

    def test_model_dump(self):
        msg = make_message()
        d = msg.model_dump()
        assert "message_id" in d
        assert "amount" in d


class TestCorrespondentBank:
    def test_valid_bank_creation(self):
        bank = CorrespondentBank(
            bank_id="cb_001",
            bic="DEUTDEDB",
            bank_name="Deutsche Bank",
            country_code="DE",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["EUR", "USD"],
            nostro_account="DE91100000000123456789",
        )
        assert bank.bank_id == "cb_001"
        assert bank.fatf_risk == "low"
        assert bank.is_active is True

    def test_fatf_risk_default_low(self):
        bank = CorrespondentBank(
            bank_id="cb_x",
            bic="BARCGB22",
            bank_name="Barclays",
            country_code="GB",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["GBP"],
        )
        assert bank.fatf_risk == "low"


class TestNostroPosition:
    def test_valid_position(self):
        pos = NostroPosition(
            position_id="pos_001",
            bank_id="cb_001",
            currency="EUR",
            our_balance=Decimal("100000.00"),
            their_balance=Decimal("100000.00"),
            snapshot_date="2026-04-20T00:00:00+00:00",
        )
        assert pos.mismatch_amount == Decimal("0")

    def test_amounts_are_decimal(self):
        pos = NostroPosition(
            position_id="pos_002",
            bank_id="cb_001",
            currency="GBP",
            our_balance=Decimal("50000"),
            their_balance=Decimal("49999"),
            snapshot_date="2026-04-20T00:00:00+00:00",
        )
        assert isinstance(pos.our_balance, Decimal)
        assert isinstance(pos.their_balance, Decimal)


class TestInMemoryStores:
    def test_message_store_save_get(self):
        store = InMemoryMessageStore()
        msg = make_message()
        store.save(msg)
        assert store.get("msg_001") == msg

    def test_message_store_list_by_status(self):
        store = InMemoryMessageStore()
        msg = make_message()
        store.save(msg)
        drafts = store.list_by_status(MessageStatus.DRAFT)
        assert len(drafts) == 1

    def test_correspondent_store_seeded(self):
        store = InMemoryCorrespondentStore()
        bank = store.get("cb_001")
        assert bank is not None
        assert bank.bank_name == "Deutsche Bank"

    def test_correspondent_store_find_by_currency(self):
        store = InMemoryCorrespondentStore()
        banks = store.find_by_currency("EUR")
        assert len(banks) >= 1

    def test_nostro_store_append_only(self):
        store = InMemoryNostroStore()
        pos = NostroPosition(
            position_id="p1",
            bank_id="cb_001",
            currency="EUR",
            our_balance=Decimal("1000"),
            their_balance=Decimal("1000"),
            snapshot_date="2026-04-20T00:00:00+00:00",
        )
        store.append(pos)
        latest = store.get_latest("cb_001", "EUR")
        assert latest is not None
        assert latest.position_id == "p1"

    def test_hitl_proposal_fields(self):
        proposal = HITLProposal(
            action="CANCEL_MESSAGE",
            message_id="msg_001",
            requires_approval_from="TREASURY_OPS",
            reason="Test reason",
        )
        assert proposal.autonomy_level == "L4"
        assert proposal.requires_approval_from == "TREASURY_OPS"
