"""
tests/test_card_issuing/test_models.py
IL-CIM-01 | Phase 19 — Domain model and InMemory stub tests.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.card_issuing.fraud_shield import FraudAssessment
from services.card_issuing.models import (
    _SAMPLE_BINS,
    AuthorisationResult,
    Card,
    CardAuthorisation,
    CardNetwork,
    CardStatus,
    CardTransaction,
    CardType,
    InMemoryCardAudit,
    InMemoryCardStore,
    InMemorySpendLimitStore,
    InMemoryTransactionStore,
    SpendLimit,
    SpendPeriod,
    TransactionType,
)

_NOW = datetime.now(UTC)


def _make_card(card_id: str = "card-001", entity_id: str = "ent-001") -> Card:
    return Card(
        id=card_id,
        entity_id=entity_id,
        card_type=CardType.VIRTUAL,
        network=CardNetwork.MASTERCARD,
        bin_range_id="bin-mc-001",
        last_four="1234",
        expiry_month=12,
        expiry_year=2028,
        status=CardStatus.PENDING,
        created_at=_NOW,
        activated_at=None,
        pin_hash=None,
        name_on_card="Test User",
    )


def _make_auth(
    auth_id: str = "auth-001",
    card_id: str = "card-001",
    amount: str = "100.00",
) -> CardAuthorisation:
    return CardAuthorisation(
        id=auth_id,
        card_id=card_id,
        amount=Decimal(amount),
        currency="GBP",
        merchant_name="Test Merchant",
        merchant_mcc="5411",
        merchant_country="GB",
        result=AuthorisationResult.APPROVED,
        decline_reason=None,
        authorised_at=_NOW,
        transaction_type=TransactionType.PURCHASE,
    )


def _make_txn(txn_id: str = "txn-001", card_id: str = "card-001") -> CardTransaction:
    return CardTransaction(
        id=txn_id,
        card_id=card_id,
        authorisation_id="auth-001",
        amount=Decimal("100.00"),
        currency="GBP",
        merchant_name="Test Merchant",
        merchant_mcc="5411",
        posted_at=_NOW,
        transaction_type=TransactionType.PURCHASE,
        settled=False,
    )


# ── Card frozen dataclass tests ────────────────────────────────────────────────


def test_card_is_frozen_dataclass() -> None:
    card = _make_card()
    with pytest.raises(FrozenInstanceError):
        card.id = "modified"  # type: ignore[misc]


def test_card_status_enum_values() -> None:
    assert CardStatus.PENDING.value == "PENDING"
    assert CardStatus.ACTIVE.value == "ACTIVE"
    assert CardStatus.FROZEN.value == "FROZEN"
    assert CardStatus.BLOCKED.value == "BLOCKED"
    assert CardStatus.EXPIRED.value == "EXPIRED"
    assert CardStatus.REPLACED.value == "REPLACED"


def test_card_type_enum_virtual_physical() -> None:
    assert CardType.VIRTUAL.value == "VIRTUAL"
    assert CardType.PHYSICAL.value == "PHYSICAL"


def test_card_network_enum_mastercard_visa() -> None:
    assert CardNetwork.MASTERCARD.value == "MASTERCARD"
    assert CardNetwork.VISA.value == "VISA"


def test_card_authorisation_amount_is_decimal() -> None:
    auth = _make_auth(amount="250.75")
    assert isinstance(auth.amount, Decimal)
    assert auth.amount == Decimal("250.75")


def test_card_authorisation_approved_result() -> None:
    auth = _make_auth()
    assert auth.result == AuthorisationResult.APPROVED
    assert auth.decline_reason is None


def test_spend_limit_with_blocked_mccs() -> None:
    limit = SpendLimit(
        card_id="card-001",
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("500.00"),
        currency="GBP",
        blocked_mccs=["7995", "6011"],
        geo_restrictions=[],
    )
    assert "7995" in limit.blocked_mccs
    assert len(limit.blocked_mccs) == 2


def test_card_transaction_settled_flag() -> None:
    txn = _make_txn()
    assert txn.settled is False


def test_fraud_assessment_is_suspicious_field() -> None:
    fa = FraudAssessment(
        card_id="card-001",
        risk_score=80.0,
        is_suspicious=True,
        triggered_rules=["HIGH_VELOCITY"],
        assessed_at=_NOW,
    )
    assert fa.is_suspicious is True
    assert fa.risk_score == 80.0


def test_sample_bins_has_two_entries() -> None:
    assert len(_SAMPLE_BINS) == 2


def test_sample_bins_networks() -> None:
    networks = {b.network for b in _SAMPLE_BINS}
    assert CardNetwork.MASTERCARD in networks
    assert CardNetwork.VISA in networks


# ── InMemoryCardStore tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_card_store_save_get() -> None:
    store = InMemoryCardStore()
    card = _make_card()
    await store.save(card)
    result = await store.get(card.id)
    assert result == card


@pytest.mark.asyncio
async def test_in_memory_card_store_get_missing_returns_none() -> None:
    store = InMemoryCardStore()
    result = await store.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_in_memory_card_store_list_by_entity() -> None:
    store = InMemoryCardStore()
    card1 = _make_card(card_id="card-001", entity_id="ent-001")
    card2 = _make_card(card_id="card-002", entity_id="ent-001")
    card3 = _make_card(card_id="card-003", entity_id="ent-002")
    await store.save(card1)
    await store.save(card2)
    await store.save(card3)
    result = await store.list_by_entity("ent-001")
    assert len(result) == 2


# ── InMemorySpendLimitStore tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_spend_limit_save_get() -> None:
    store = InMemorySpendLimitStore()
    limit = SpendLimit(
        card_id="card-001",
        period=SpendPeriod.PER_TRANSACTION,
        limit_amount=Decimal("1000"),
        currency="GBP",
        blocked_mccs=[],
        geo_restrictions=[],
    )
    await store.save(limit)
    result = await store.get("card-001")
    assert result == limit


@pytest.mark.asyncio
async def test_in_memory_spend_limit_get_missing_returns_none() -> None:
    store = InMemorySpendLimitStore()
    result = await store.get("nonexistent")
    assert result is None


# ── InMemoryTransactionStore tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_txn_store_save_auth_list_auths() -> None:
    store = InMemoryTransactionStore()
    auth = _make_auth()
    await store.save_auth(auth)
    results = await store.list_auths("card-001")
    assert len(results) == 1
    assert results[0].id == "auth-001"


@pytest.mark.asyncio
async def test_in_memory_txn_store_get_auth() -> None:
    store = InMemoryTransactionStore()
    auth = _make_auth()
    await store.save_auth(auth)
    result = await store.get_auth("auth-001")
    assert result is not None
    assert result.id == "auth-001"


@pytest.mark.asyncio
async def test_in_memory_txn_store_get_auth_missing_returns_none() -> None:
    store = InMemoryTransactionStore()
    result = await store.get_auth("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_in_memory_txn_store_save_txn_list_txns() -> None:
    store = InMemoryTransactionStore()
    txn = _make_txn()
    await store.save_txn(txn)
    results = await store.list_txns("card-001")
    assert len(results) == 1
    assert results[0].id == "txn-001"


# ── InMemoryCardAudit tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_audit_log_and_list() -> None:
    audit = InMemoryCardAudit()
    await audit.log("card.issued", "card-001", "ent-001", "admin", {})
    events = await audit.list_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "card.issued"


@pytest.mark.asyncio
async def test_in_memory_audit_filter_by_card_id() -> None:
    audit = InMemoryCardAudit()
    await audit.log("card.issued", "card-001", "ent-001", "admin", {})
    await audit.log("card.issued", "card-002", "ent-001", "admin", {})
    events = await audit.list_events(card_id="card-001")
    assert len(events) == 1
    assert events[0]["card_id"] == "card-001"


@pytest.mark.asyncio
async def test_in_memory_audit_list_all_no_filter() -> None:
    audit = InMemoryCardAudit()
    await audit.log("card.issued", "card-001", "ent-001", "admin", {})
    await audit.log("card.activated", "card-002", "ent-001", "admin", {})
    events = await audit.list_events(card_id=None)
    assert len(events) == 2
