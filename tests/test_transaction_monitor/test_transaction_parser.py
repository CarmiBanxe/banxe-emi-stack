"""
tests/test_transaction_monitor/test_transaction_parser.py
IL-RTM-01 | banxe-emi-stack

Tests for TransactionParser: valid parsing, ParseError on bad input,
Decimal amount enforcement, and transaction type defaults.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.transaction_monitor.consumer.transaction_parser import (
    ParseError,
    TransactionParser,
)
from services.transaction_monitor.models.transaction import TransactionType


class TestTransactionParser:
    def setup_method(self):
        self.parser = TransactionParser()

    def test_parse_valid_event(self):
        payload = {
            "transaction_id": "TXN-2026-001",
            "amount": "15200.00",
            "sender_id": "cust-001",
            "sender_jurisdiction": "GB",
            "receiver_jurisdiction": "AE",
            "transaction_type": "transfer",
        }
        event = self.parser.parse(payload)
        assert event.transaction_id == "TXN-2026-001"
        assert event.amount == Decimal("15200.00")
        assert isinstance(event.amount, Decimal)
        assert event.sender_jurisdiction == "GB"
        assert event.receiver_jurisdiction == "AE"

    def test_parse_amount_as_integer(self):
        payload = {
            "transaction_id": "TXN-INT",
            "amount": 5000,
            "sender_id": "cust-002",
        }
        event = self.parser.parse(payload)
        assert event.amount == Decimal("5000")

    def test_parse_missing_amount_raises_parse_error(self):
        with pytest.raises(ParseError, match="amount"):
            self.parser.parse({"transaction_id": "TXN-X", "sender_id": "cust-X"})

    def test_parse_negative_amount_raises_parse_error(self):
        with pytest.raises(ParseError, match="positive"):
            self.parser.parse(
                {
                    "transaction_id": "TXN-NEG",
                    "amount": "-100.00",
                    "sender_id": "cust-003",
                }
            )

    def test_parse_invalid_amount_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(
                {
                    "transaction_id": "TXN-BAD",
                    "amount": "not-a-number",
                    "sender_id": "cust-004",
                }
            )

    def test_parse_missing_transaction_id_raises_parse_error(self):
        with pytest.raises(ParseError, match="transaction_id"):
            self.parser.parse({"amount": "100.00", "sender_id": "cust-005"})

    def test_parse_defaults_transaction_type_to_payment(self):
        event = self.parser.parse(
            {
                "transaction_id": "TXN-DEF",
                "amount": "200.00",
                "sender_id": "cust-006",
                "transaction_type": "unknown_type",
            }
        )
        assert event.transaction_type == TransactionType.PAYMENT

    def test_parse_crypto_onramp_type(self):
        event = self.parser.parse(
            {
                "transaction_id": "TXN-CRYPTO",
                "amount": "3000.00",
                "sender_id": "cust-007",
                "transaction_type": "crypto_onramp",
            }
        )
        assert event.transaction_type == TransactionType.CRYPTO_ONRAMP
