"""
tests/test_dispute_resolution/test_chargeback_bridge.py
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.dispute_resolution.chargeback_bridge import ChargebackBridge
from services.dispute_resolution.models import InMemoryChargebackStore


def _bridge() -> ChargebackBridge:
    return ChargebackBridge(store=InMemoryChargebackStore())


class TestInitiateChargeback:
    def test_returns_chargeback_id(self) -> None:
        bridge = _bridge()
        result = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        assert result["chargeback_id"] != ""

    def test_visa_scheme_accepted(self) -> None:
        bridge = _bridge()
        result = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        assert result["scheme"] == "VISA"

    def test_mastercard_scheme_accepted(self) -> None:
        bridge = _bridge()
        result = bridge.initiate_chargeback("d-001", "MASTERCARD", Decimal("50.00"), "4853")
        assert result["scheme"] == "MASTERCARD"

    def test_invalid_scheme_raises(self) -> None:
        bridge = _bridge()
        with pytest.raises(ValueError, match="Unknown scheme"):
            bridge.initiate_chargeback("d-001", "AMEX", Decimal("100.00"), "4853")

    def test_zero_amount_raises(self) -> None:
        bridge = _bridge()
        with pytest.raises(ValueError, match="positive"):
            bridge.initiate_chargeback("d-001", "VISA", Decimal("0"), "4853")

    def test_negative_amount_raises(self) -> None:
        bridge = _bridge()
        with pytest.raises(ValueError, match="positive"):
            bridge.initiate_chargeback("d-001", "VISA", Decimal("-10.00"), "4853")

    def test_status_initiated(self) -> None:
        bridge = _bridge()
        result = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        assert result["status"] == "INITIATED"

    def test_amount_as_string(self) -> None:
        bridge = _bridge()
        result = bridge.initiate_chargeback("d-001", "VISA", Decimal("99.99"), "4853")
        assert result["amount"] == "99.99"


class TestSubmitRepresentment:
    def test_status_representment_submitted(self) -> None:
        bridge = _bridge()
        cb = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        result = bridge.submit_representment(cb["chargeback_id"], ["hash1", "hash2"])
        assert result["status"] == "REPRESENTMENT_SUBMITTED"

    def test_evidence_count_in_result(self) -> None:
        bridge = _bridge()
        cb = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        result = bridge.submit_representment(cb["chargeback_id"], ["h1", "h2", "h3"])
        assert result["evidence_count"] == 3

    def test_unknown_chargeback_raises(self) -> None:
        bridge = _bridge()
        with pytest.raises(ValueError, match="not found"):
            bridge.submit_representment("nonexistent", [])


class TestGetChargebackStatus:
    def test_returns_status(self) -> None:
        bridge = _bridge()
        cb = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        result = bridge.get_chargeback_status(cb["chargeback_id"])
        assert result["status"] == "INITIATED"

    def test_dispute_id_in_result(self) -> None:
        bridge = _bridge()
        cb = bridge.initiate_chargeback("d-001", "VISA", Decimal("100.00"), "4853")
        result = bridge.get_chargeback_status(cb["chargeback_id"])
        assert result["dispute_id"] == "d-001"

    def test_amount_as_string(self) -> None:
        bridge = _bridge()
        cb = bridge.initiate_chargeback("d-001", "VISA", Decimal("75.00"), "4853")
        result = bridge.get_chargeback_status(cb["chargeback_id"])
        assert result["amount"] == "75.00"

    def test_unknown_raises(self) -> None:
        bridge = _bridge()
        with pytest.raises(ValueError, match="not found"):
            bridge.get_chargeback_status("nonexistent")


class TestListChargebacksForDispute:
    def test_empty_dispute(self) -> None:
        bridge = _bridge()
        result = bridge.list_chargebacks_for_dispute("d-empty")
        assert result["count"] == 0

    def test_count_matches(self) -> None:
        bridge = _bridge()
        bridge.initiate_chargeback("d-001", "VISA", Decimal("50.00"), "4853")
        bridge.initiate_chargeback("d-001", "MASTERCARD", Decimal("75.00"), "4853")
        result = bridge.list_chargebacks_for_dispute("d-001")
        assert result["count"] == 2

    def test_chargebacks_list_present(self) -> None:
        bridge = _bridge()
        bridge.initiate_chargeback("d-001", "VISA", Decimal("50.00"), "4853")
        result = bridge.list_chargebacks_for_dispute("d-001")
        assert len(result["chargebacks"]) == 1
        assert result["chargebacks"][0]["scheme"] == "VISA"
