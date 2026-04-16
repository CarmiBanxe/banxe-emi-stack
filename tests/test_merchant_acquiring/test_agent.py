"""
tests/test_merchant_acquiring/test_agent.py
IL-MAG-01 | Phase 20 — MerchantAgent orchestrator tests.
"""

from __future__ import annotations

import pytest

from services.merchant_acquiring.chargeback_handler import ChargebackHandler
from services.merchant_acquiring.merchant_agent import MerchantAgent
from services.merchant_acquiring.merchant_onboarding import MerchantOnboarding
from services.merchant_acquiring.merchant_risk_scorer import MerchantRiskScorer
from services.merchant_acquiring.models import (
    InMemoryDisputeStore,
    InMemoryMAAudit,
    InMemoryMerchantStore,
    InMemoryPaymentStore,
    InMemorySettlementStore,
)
from services.merchant_acquiring.payment_gateway import PaymentGateway
from services.merchant_acquiring.settlement_engine import SettlementEngine


def _make_agent() -> MerchantAgent:
    merchant_store = InMemoryMerchantStore()
    payment_store = InMemoryPaymentStore()
    settlement_store = InMemorySettlementStore()
    dispute_store = InMemoryDisputeStore()
    audit = InMemoryMAAudit()

    onboarding = MerchantOnboarding(merchant_store, audit)
    gateway = PaymentGateway(merchant_store, payment_store, audit)
    settlement = SettlementEngine(payment_store, settlement_store, audit)
    chargeback = ChargebackHandler(dispute_store, audit)
    risk_scorer = MerchantRiskScorer(merchant_store, payment_store, dispute_store, audit)

    return MerchantAgent(onboarding, gateway, settlement, chargeback, risk_scorer, audit)


@pytest.mark.asyncio
async def test_onboard_merchant_returns_dict_with_id() -> None:
    agent = _make_agent()
    result = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    assert "id" in result
    assert result["id"] != ""


@pytest.mark.asyncio
async def test_onboard_merchant_prohibited_mcc_raises_value_error() -> None:
    agent = _make_agent()
    with pytest.raises(ValueError):
        await agent.onboard_merchant(
            "Casino", "Casino Ltd", "7995", "GB", None, "5000", "100000", "admin"
        )


@pytest.mark.asyncio
async def test_approve_kyb_returns_dict_with_active_status() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    approved = await agent.approve_kyb(m["id"], "admin")
    assert approved["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_accept_payment_returns_dict_with_result() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    await agent.approve_kyb(m["id"], "admin")
    p = await agent.accept_payment(m["id"], "20.00", "GBP", "4242", "ref", "admin")
    assert "result" in p


@pytest.mark.asyncio
async def test_accept_payment_large_amount_pending_3ds() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    await agent.approve_kyb(m["id"], "admin")
    p = await agent.accept_payment(m["id"], "100.00", "GBP", "4242", "ref", "admin")
    assert p["result"] == "PENDING_3DS"


@pytest.mark.asyncio
async def test_complete_3ds_returns_approved_result() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    await agent.approve_kyb(m["id"], "admin")
    p = await agent.accept_payment(m["id"], "100.00", "GBP", "4242", "ref", "admin")
    completed = await agent.complete_3ds(p["id"], "admin")
    assert completed["result"] == "APPROVED"


@pytest.mark.asyncio
async def test_create_settlement_returns_dict_with_net_amount() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    await agent.approve_kyb(m["id"], "admin")
    await agent.accept_payment(m["id"], "20.00", "GBP", "4242", "ref", "admin")
    s = await agent.create_settlement(m["id"], "admin")
    assert "net_amount" in s


@pytest.mark.asyncio
async def test_list_settlements_returns_list() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    await agent.approve_kyb(m["id"], "admin")
    await agent.accept_payment(m["id"], "20.00", "GBP", "4242", "ref", "admin")
    await agent.create_settlement(m["id"], "admin")
    result = await agent.list_settlements(m["id"])
    assert isinstance(result, list)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_receive_chargeback_returns_dict_with_received_status() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    d = await agent.receive_chargeback(m["id"], "p-001", "25.00", "GBP", "FRAUD", "admin")
    assert d["status"] == "RECEIVED"


@pytest.mark.asyncio
async def test_resolve_dispute_returns_resolved_win() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    d = await agent.receive_chargeback(m["id"], "p-001", "25.00", "GBP", "FRAUD", "admin")
    resolved = await agent.resolve_dispute(d["id"], won=True, actor="admin")
    assert resolved["status"] == "RESOLVED_WIN"


@pytest.mark.asyncio
async def test_score_merchant_returns_dict_with_overall_score() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    score = await agent.score_merchant(m["id"])
    assert "overall_score" in score


@pytest.mark.asyncio
async def test_get_merchant_returns_dict() -> None:
    agent = _make_agent()
    m = await agent.onboard_merchant(
        "Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    found = await agent.get_merchant(m["id"])
    assert found is not None
    assert found["id"] == m["id"]


@pytest.mark.asyncio
async def test_get_merchant_returns_none_for_missing() -> None:
    agent = _make_agent()
    result = await agent.get_merchant("no-such-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_merchants_returns_list() -> None:
    agent = _make_agent()
    await agent.onboard_merchant("Shop1", "S1 Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await agent.onboard_merchant("Shop2", "S2 Ltd", "5411", "GB", None, "5000", "100000", "admin")
    result = await agent.list_merchants()
    assert isinstance(result, list)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_audit_log_returns_list_of_dicts() -> None:
    agent = _make_agent()
    await agent.onboard_merchant("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    log = await agent.get_audit_log()
    assert isinstance(log, list)
    assert len(log) > 0
    assert isinstance(log[0], dict)


@pytest.mark.asyncio
async def test_full_flow_onboard_approve_payment_settle() -> None:
    agent = _make_agent()
    # Onboard
    m = await agent.onboard_merchant(
        "FullFlow", "FF Ltd", "5411", "GB", None, "5000", "100000", "admin"
    )
    assert m["status"] == "PENDING_KYB"
    # Approve
    approved = await agent.approve_kyb(m["id"], "admin")
    assert approved["status"] == "ACTIVE"
    # Accept payment
    p = await agent.accept_payment(m["id"], "20.00", "GBP", "4242", "ref", "admin")
    assert p["result"] == "APPROVED"
    # Settle
    s = await agent.create_settlement(m["id"], "admin")
    assert s["gross_amount"] == "20.00"
    assert s["payment_count"] == 1
