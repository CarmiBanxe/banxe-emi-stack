"""
tests/test_card_issuing/test_spend_control.py
IL-CIM-01 | Phase 19 — SpendControl unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.card_issuing.models import (
    CardTransaction,
    InMemoryCardAudit,
    InMemorySpendLimitStore,
    InMemoryTransactionStore,
    SpendPeriod,
    TransactionType,
)
from services.card_issuing.spend_control import SpendControl


def _make_spend_control() -> tuple[
    SpendControl, InMemorySpendLimitStore, InMemoryTransactionStore, InMemoryCardAudit
]:
    limit_store = InMemorySpendLimitStore()
    txn_store = InMemoryTransactionStore()
    audit = InMemoryCardAudit()
    sc = SpendControl(limit_store, txn_store, audit)
    return sc, limit_store, txn_store, audit


def _make_txn(card_id: str, amount: str = "50.00") -> CardTransaction:
    return CardTransaction(
        id="txn-001",
        card_id=card_id,
        authorisation_id="auth-001",
        amount=Decimal(amount),
        currency="GBP",
        merchant_name="Merchant",
        merchant_mcc="5411",
        posted_at=datetime.now(UTC),
        transaction_type=TransactionType.PURCHASE,
        settled=False,
    )


# ── set_limits tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_limits_creates_spend_limit() -> None:
    sc, limit_store, _, _ = _make_spend_control()
    limit = await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "500.00", "GBP")
    assert limit.card_id == "card-001"
    assert limit.period == SpendPeriod.PER_TRANSACTION


@pytest.mark.asyncio
async def test_set_limits_amount_parsed_from_string_to_decimal() -> None:
    sc, _, _, _ = _make_spend_control()
    limit = await sc.set_limits("card-001", SpendPeriod.DAILY, "1250.50", "GBP")
    assert isinstance(limit.limit_amount, Decimal)
    assert limit.limit_amount == Decimal("1250.50")


@pytest.mark.asyncio
async def test_set_limits_creates_audit_entry() -> None:
    sc, _, _, audit = _make_spend_control()
    await sc.set_limits("card-001", SpendPeriod.MONTHLY, "5000.00", "GBP")
    events = await audit.list_events()
    assert any(e["event_type"] == "card.limits_set" for e in events)


# ── get_limits tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_limits_returns_saved_limit() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "300.00", "GBP")
    limit = await sc.get_limits("card-001")
    assert limit is not None
    assert limit.limit_amount == Decimal("300.00")


@pytest.mark.asyncio
async def test_get_limits_none_for_unknown_card() -> None:
    sc, _, _, _ = _make_spend_control()
    result = await sc.get_limits("nonexistent")
    assert result is None


# ── check_authorisation tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_authorisation_under_limit_returns_true() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "500.00", "GBP")
    allowed, reason = await sc.check_authorisation(
        "card-001", Decimal("100.00"), "GBP", "5411", "GB"
    )
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_check_authorisation_over_per_txn_limit_returns_false() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "100.00", "GBP")
    allowed, reason = await sc.check_authorisation(
        "card-001", Decimal("200.00"), "GBP", "5411", "GB"
    )
    assert allowed is False
    assert "limit" in reason.lower() or "exceed" in reason.lower() or "200" in reason


@pytest.mark.asyncio
async def test_check_authorisation_blocked_mcc_returns_false() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits(
        "card-001", SpendPeriod.PER_TRANSACTION, "1000.00", "GBP", blocked_mccs=["7995"]
    )
    allowed, reason = await sc.check_authorisation(
        "card-001", Decimal("10.00"), "GBP", "7995", "GB"
    )
    assert allowed is False
    assert "7995" in reason


@pytest.mark.asyncio
async def test_check_authorisation_geo_restricted_returns_false() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits(
        "card-001", SpendPeriod.PER_TRANSACTION, "1000.00", "GBP", geo_restrictions=["US"]
    )
    allowed, reason = await sc.check_authorisation(
        "card-001", Decimal("10.00"), "GBP", "5411", "US"
    )
    assert allowed is False
    assert "US" in reason


@pytest.mark.asyncio
async def test_check_authorisation_no_limits_permissive() -> None:
    sc, _, _, _ = _make_spend_control()
    allowed, reason = await sc.check_authorisation(
        "card-001", Decimal("9999.99"), "GBP", "7995", "US"
    )
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_check_authorisation_empty_blocked_mccs_allows_all() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "500.00", "GBP", blocked_mccs=[])
    allowed, _ = await sc.check_authorisation("card-001", Decimal("10.00"), "GBP", "7995", "GB")
    assert allowed is True


@pytest.mark.asyncio
async def test_check_authorisation_empty_geo_restrictions_allows_all() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits(
        "card-001", SpendPeriod.PER_TRANSACTION, "500.00", "GBP", geo_restrictions=[]
    )
    allowed, _ = await sc.check_authorisation("card-001", Decimal("10.00"), "GBP", "5411", "CN")
    assert allowed is True


# ── get_daily_spent tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_daily_spent_zero_with_no_transactions() -> None:
    sc, _, _, _ = _make_spend_control()
    total = await sc.get_daily_spent("card-001", "GBP")
    assert total == Decimal("0")


@pytest.mark.asyncio
async def test_get_daily_spent_sums_today_purchases() -> None:
    sc, _, txn_store, _ = _make_spend_control()
    await txn_store.save_txn(_make_txn("card-001", "100.00"))
    await txn_store.save_txn(_make_txn("card-001", "50.00"))
    total = await sc.get_daily_spent("card-001", "GBP")
    assert total == Decimal("150.00")


# ── get_monthly_spent tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_monthly_spent_zero_with_no_transactions() -> None:
    sc, _, _, _ = _make_spend_control()
    total = await sc.get_monthly_spent("card-001", "GBP")
    assert total == Decimal("0")


@pytest.mark.asyncio
async def test_get_monthly_spent_sums_this_month_purchases() -> None:
    sc, _, txn_store, _ = _make_spend_control()
    await txn_store.save_txn(_make_txn("card-001", "200.00"))
    await txn_store.save_txn(_make_txn("card-001", "300.00"))
    total = await sc.get_monthly_spent("card-001", "GBP")
    assert total == Decimal("500.00")


# ── multiple limits override tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_limits_override_previous() -> None:
    sc, _, _, _ = _make_spend_control()
    await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "500.00", "GBP")
    await sc.set_limits("card-001", SpendPeriod.PER_TRANSACTION, "200.00", "GBP")
    limit = await sc.get_limits("card-001")
    assert limit is not None
    assert limit.limit_amount == Decimal("200.00")
