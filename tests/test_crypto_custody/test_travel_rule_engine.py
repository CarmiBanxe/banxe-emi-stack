"""
tests/test_crypto_custody/test_travel_rule_engine.py — Tests for TravelRuleEngine
IL-CDC-01 | Phase 35 | 18 tests
I-02: Blocked jurisdictions. I-03: FATF greylist EDD.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.crypto_custody.models import AssetType, InMemoryAuditStore, TravelRuleData
from services.crypto_custody.travel_rule_engine import (
    BLOCKED_JURISDICTIONS,
    TRAVEL_RULE_THRESHOLD_EUR,
    TravelRuleEngine,
)


@pytest.fixture()
def engine():
    return TravelRuleEngine(audit_port=InMemoryAuditStore())


def test_travel_rule_threshold_is_1000_eur(engine):
    assert Decimal("1000") == TRAVEL_RULE_THRESHOLD_EUR


def test_requires_travel_rule_at_threshold(engine):
    assert engine.requires_travel_rule(Decimal("1000")) is True


def test_requires_travel_rule_above_threshold(engine):
    assert engine.requires_travel_rule(Decimal("1500")) is True


def test_does_not_require_travel_rule_below_threshold(engine):
    assert engine.requires_travel_rule(Decimal("999.99")) is False


def test_screen_jurisdiction_pass_gb(engine):
    assert engine.screen_jurisdiction("GB") == "PASS"


def test_screen_jurisdiction_pass_de(engine):
    assert engine.screen_jurisdiction("DE") == "PASS"


def test_screen_jurisdiction_blocked_ru(engine):
    assert engine.screen_jurisdiction("RU") == "BLOCKED"


def test_screen_jurisdiction_blocked_ir(engine):
    assert engine.screen_jurisdiction("IR") == "BLOCKED"


def test_screen_jurisdiction_blocked_kp(engine):
    assert engine.screen_jurisdiction("KP") == "BLOCKED"


def test_screen_jurisdiction_blocked_by(engine):
    assert engine.screen_jurisdiction("BY") == "BLOCKED"


def test_screen_jurisdiction_blocked_sy(engine):
    assert engine.screen_jurisdiction("SY") == "BLOCKED"


def test_screen_jurisdiction_edd_required_ng(engine):
    result = engine.screen_jurisdiction("NG")
    assert result == "EDD_REQUIRED"


def test_screen_jurisdiction_case_insensitive(engine):
    assert engine.screen_jurisdiction("ru") == "BLOCKED"


def test_attach_originator_data(engine):
    data = TravelRuleData(
        originator_name="Alice",
        originator_iban="GB29NWBK60161331926819",
        originator_address="1 Main St",
        beneficiary_name="Bob",
        beneficiary_vasp="vasp-001",
        amount=Decimal("1500"),
        asset_type=AssetType.ETH,
        jurisdiction="DE",
    )
    engine.attach_originator_data("txfr-001", data)
    retrieved = engine.get_travel_rule_data("txfr-001")
    assert retrieved is not None
    assert retrieved.originator_name == "Alice"


def test_get_travel_rule_data_missing_returns_none(engine):
    assert engine.get_travel_rule_data("txfr-nonexistent") is None


def test_validate_travel_rule_complete_true(engine):
    data = TravelRuleData(
        originator_name="Alice",
        originator_iban="GB29NWBK60161331926819",
        originator_address="1 Main St",
        beneficiary_name="Bob",
        beneficiary_vasp="vasp-001",
        amount=Decimal("1500"),
        asset_type=AssetType.ETH,
        jurisdiction="DE",
    )
    engine.attach_originator_data("txfr-complete", data)
    assert engine.validate_travel_rule_complete("txfr-complete") is True


def test_validate_travel_rule_complete_false_no_data(engine):
    assert engine.validate_travel_rule_complete("txfr-no-data") is False


def test_blocked_jurisdictions_set_contains_all_9(engine):
    expected = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
    assert expected.issubset(BLOCKED_JURISDICTIONS)
