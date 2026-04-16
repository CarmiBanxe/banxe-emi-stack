"""
tests/test_card_issuing/test_fraud_shield.py
IL-CIM-01 | Phase 19 -- FraudShield unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.card_issuing.fraud_shield import FraudShield
from services.card_issuing.models import (
    AuthorisationResult,
    CardAuthorisation,
    InMemoryCardAudit,
    InMemoryTransactionStore,
    TransactionType,
)


def _make_fraud_shield(
    threshold: float = 70.0,
) -> tuple[FraudShield, InMemoryTransactionStore, InMemoryCardAudit]:
    txn_store = InMemoryTransactionStore()
    audit = InMemoryCardAudit()
    shield = FraudShield(txn_store, audit, suspicious_threshold=threshold)
    return shield, txn_store, audit


def _make_auth(card_id: str, minutes_ago: int = 0) -> CardAuthorisation:
    ts = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return CardAuthorisation(
        id=f"auth-{minutes_ago}-{card_id}",
        card_id=card_id,
        amount=Decimal("10.00"),
        currency="GBP",
        merchant_name="Merchant",
        merchant_mcc="5411",
        merchant_country="GB",
        result=AuthorisationResult.APPROVED,
        decline_reason=None,
        authorised_at=ts,
        transaction_type=TransactionType.PURCHASE,
    )


@pytest.mark.asyncio
async def test_assess_returns_fraud_assessment() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("50.00"), "5411", "GB")
    assert result.card_id == "card-001"
    assert isinstance(result.risk_score, float)


@pytest.mark.asyncio
async def test_assess_low_value_non_risky_not_suspicious() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    assert result.is_suspicious is False


@pytest.mark.asyncio
async def test_assess_high_value_increases_score() -> None:
    shield, _, _ = _make_fraud_shield()
    low = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    high = await shield.assess("card-002", Decimal("1500.00"), "5411", "GB")
    assert high.risk_score > low.risk_score


@pytest.mark.asyncio
async def test_assess_high_risk_mcc_increases_score() -> None:
    shield, _, _ = _make_fraud_shield()
    normal = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    risky = await shield.assess("card-002", Decimal("10.00"), "7995", "GB")
    assert risky.risk_score > normal.risk_score


@pytest.mark.asyncio
async def test_assess_5_auths_in_hour_triggers_high_velocity() -> None:
    shield, txn_store, _ = _make_fraud_shield()
    for i in range(5):
        await txn_store.save_auth(_make_auth("card-001", minutes_ago=i))
    result = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    assert "HIGH_VELOCITY" in result.triggered_rules


@pytest.mark.asyncio
async def test_assess_creates_audit_entry() -> None:
    shield, _, audit = _make_fraud_shield()
    await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    events = await audit.list_events()
    assert any(e["event_type"] == "fraud.assessed" for e in events)


@pytest.mark.asyncio
async def test_flag_suspicious_creates_audit_entry() -> None:
    shield, _, audit = _make_fraud_shield()
    await shield.flag_suspicious("card-001", "unusual pattern", "admin")
    events = await audit.list_events()
    assert any(e["event_type"] == "fraud.flagged" for e in events)


@pytest.mark.asyncio
async def test_triggered_rules_is_list() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    assert isinstance(result.triggered_rules, list)


@pytest.mark.asyncio
async def test_risk_score_is_float_not_decimal() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    assert isinstance(result.risk_score, float)


@pytest.mark.asyncio
async def test_assess_amount_zero_not_suspicious() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("0"), "5411", "GB")
    assert result.is_suspicious is False


@pytest.mark.asyncio
async def test_fraud_assessment_assessed_at_is_recent() -> None:
    shield, _, _ = _make_fraud_shield()
    before = datetime.now(UTC)
    result = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    after = datetime.now(UTC)
    assert before <= result.assessed_at <= after


@pytest.mark.asyncio
async def test_high_velocity_high_amount_risky_mcc_is_suspicious() -> None:
    shield, txn_store, _ = _make_fraud_shield(threshold=70.0)
    for i in range(5):
        await txn_store.save_auth(_make_auth("card-001", minutes_ago=i))
    result = await shield.assess("card-001", Decimal("1500.00"), "7995", "GB")
    assert result.is_suspicious is True


@pytest.mark.asyncio
async def test_normal_transaction_not_suspicious() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("25.00"), "5411", "GB")
    assert result.is_suspicious is False


@pytest.mark.asyncio
async def test_assessed_at_is_utc() -> None:
    shield, _, _ = _make_fraud_shield()
    result = await shield.assess("card-001", Decimal("10.00"), "5411", "GB")
    assert result.assessed_at.tzinfo is not None
    assert result.assessed_at.tzinfo == UTC
