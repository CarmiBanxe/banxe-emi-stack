"""
tests/test_card_issuing/test_agent.py
IL-CIM-01 | Phase 19 -- CardAgent unit tests.
"""

from __future__ import annotations

import pytest

from services.card_issuing.card_agent import CardAgent
from services.card_issuing.card_issuer import CardIssuer
from services.card_issuing.card_lifecycle import CardLifecycle
from services.card_issuing.card_transaction_processor import CardTransactionProcessor
from services.card_issuing.fraud_shield import FraudShield
from services.card_issuing.models import (
    InMemoryCardAudit,
    InMemoryCardStore,
    InMemorySpendLimitStore,
    InMemoryTransactionStore,
)
from services.card_issuing.spend_control import SpendControl


def _make_agent() -> CardAgent:
    card_store = InMemoryCardStore()
    limit_store = InMemorySpendLimitStore()
    txn_store = InMemoryTransactionStore()
    audit = InMemoryCardAudit()
    issuer = CardIssuer(card_store, audit)
    lifecycle = CardLifecycle(card_store, audit)
    sc = SpendControl(limit_store, txn_store, audit)
    processor = CardTransactionProcessor(card_store, txn_store, sc, audit)
    fraud_shield = FraudShield(txn_store, audit)
    return CardAgent(issuer, lifecycle, sc, processor, fraud_shield, audit)


@pytest.mark.asyncio
async def test_issue_card_returns_dict_with_id() -> None:
    agent = _make_agent()
    result = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    assert "id" in result
    assert result["id"].startswith("card-")


@pytest.mark.asyncio
async def test_issue_card_status_is_pending() -> None:
    agent = _make_agent()
    result = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    assert result["status"] == "PENDING"


@pytest.mark.asyncio
async def test_activate_card_status_becomes_active() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    activated = await agent.activate_card(issued["id"], "admin")
    assert activated["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_set_pin_returns_dict_with_success() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    result = await agent.set_pin(issued["id"], "4321", "admin")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_freeze_card_status_frozen() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    await agent.activate_card(issued["id"], "admin")
    frozen = await agent.freeze_card(issued["id"], "admin")
    assert frozen["status"] == "FROZEN"


@pytest.mark.asyncio
async def test_unfreeze_card_status_active() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    await agent.activate_card(issued["id"], "admin")
    await agent.freeze_card(issued["id"], "admin")
    unfrozen = await agent.unfreeze_card(issued["id"], "admin")
    assert unfrozen["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_block_card_status_blocked() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    await agent.activate_card(issued["id"], "admin")
    blocked = await agent.block_card(issued["id"], "admin", "fraud")
    assert blocked["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_set_limits_returns_limit_info() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    result = await agent.set_limits(issued["id"], "PER_TRANSACTION", "500.00", "GBP", [], "admin")
    assert result["card_id"] == issued["id"]
    assert result["limit_amount"] == "500.00"


@pytest.mark.asyncio
async def test_authorise_transaction_returns_dict_with_result() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    await agent.activate_card(issued["id"], "admin")
    result = await agent.authorise_transaction(
        issued["id"], "50.00", "GBP", "Tesco", "5411", "GB", "pos"
    )
    assert "result" in result


@pytest.mark.asyncio
async def test_authorise_transaction_approved_for_active_card() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    await agent.activate_card(issued["id"], "admin")
    result = await agent.authorise_transaction(
        issued["id"], "50.00", "GBP", "Tesco", "5411", "GB", "pos"
    )
    assert result["result"] == "APPROVED"


@pytest.mark.asyncio
async def test_get_card_returns_dict_or_none() -> None:
    agent = _make_agent()
    result = await agent.get_card("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_card_returns_dict_for_existing() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    result = await agent.get_card(issued["id"])
    assert result is not None
    assert result["id"] == issued["id"]


@pytest.mark.asyncio
async def test_list_cards_returns_list() -> None:
    agent = _make_agent()
    await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    await agent.issue_card("ent-001", "PHYSICAL", "VISA", "A User", "admin")
    cards = await agent.list_cards("ent-001")
    assert isinstance(cards, list)
    assert len(cards) == 2


@pytest.mark.asyncio
async def test_list_transactions_returns_list() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    txns = await agent.list_transactions(issued["id"])
    assert isinstance(txns, list)


@pytest.mark.asyncio
async def test_get_fraud_assessment_returns_dict_with_risk_score() -> None:
    agent = _make_agent()
    result = await agent.get_fraud_assessment("card-001", "100.00", "5411", "GB")
    assert "risk_score" in result
    assert isinstance(result["risk_score"], float)


@pytest.mark.asyncio
async def test_get_audit_log_returns_list() -> None:
    agent = _make_agent()
    await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    log = await agent.get_audit_log()
    assert isinstance(log, list)
    assert len(log) > 0


@pytest.mark.asyncio
async def test_full_flow_issue_activate_authorise_list_transactions() -> None:
    agent = _make_agent()
    issued = await agent.issue_card("ent-001", "VIRTUAL", "MASTERCARD", "A User", "admin")
    assert issued["status"] == "PENDING"

    activated = await agent.activate_card(issued["id"], "admin")
    assert activated["status"] == "ACTIVE"

    auth = await agent.authorise_transaction(
        issued["id"], "75.00", "GBP", "Amazon", "5999", "GB", "pos"
    )
    assert auth["result"] == "APPROVED"

    txns = await agent.list_transactions(issued["id"])
    assert isinstance(txns, list)
