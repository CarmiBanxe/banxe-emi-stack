"""
tests/test_scheduled_payments/test_direct_debit_engine.py — Unit tests for DirectDebitEngine
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.scheduled_payments.direct_debit_engine import DirectDebitEngine


@pytest.fixture()
def engine() -> DirectDebitEngine:
    return DirectDebitEngine()


def _create_mandate(engine: DirectDebitEngine, customer_id: str = "cust-1") -> str:
    result = engine.create_mandate(
        customer_id=customer_id,
        creditor_id="cred-1",
        creditor_name="Test Creditor",
        scheme_ref="REF-001",
        service_user_number="123456",
    )
    return result["mandate_id"]


# ── create_mandate ─────────────────────────────────────────────────────────────


def test_create_mandate_returns_mandate_id(engine: DirectDebitEngine) -> None:
    result = engine.create_mandate("c1", "cr1", "Name", "SR1", "111")
    assert result["mandate_id"] != ""


def test_create_mandate_status_pending(engine: DirectDebitEngine) -> None:
    result = engine.create_mandate("c1", "cr1", "Name", "SR1", "111")
    assert result["status"] == "PENDING"


def test_create_mandate_returns_creditor_name(engine: DirectDebitEngine) -> None:
    result = engine.create_mandate("c1", "cr1", "My Creditor", "SR1", "111")
    assert result["creditor_name"] == "My Creditor"


# ── authorise_mandate ──────────────────────────────────────────────────────────


def test_authorise_mandate_returns_authorised(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    result = engine.authorise_mandate(m_id)
    assert result["status"] == "AUTHORISED"


def test_authorise_mandate_sets_authorised_at(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    result = engine.authorise_mandate(m_id)
    assert result["authorised_at"] is not None


def test_authorise_mandate_non_pending_raises(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    engine.authorise_mandate(m_id)
    with pytest.raises(ValueError, match="not PENDING"):
        engine.authorise_mandate(m_id)


def test_authorise_mandate_not_found_raises(engine: DirectDebitEngine) -> None:
    with pytest.raises(ValueError, match="not found"):
        engine.authorise_mandate("nonexistent")


# ── activate_mandate ───────────────────────────────────────────────────────────


def test_activate_mandate_returns_active(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    engine.authorise_mandate(m_id)
    result = engine.activate_mandate(m_id)
    assert result["status"] == "ACTIVE"


def test_activate_mandate_non_authorised_raises(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    with pytest.raises(ValueError, match="AUTHORISED"):
        engine.activate_mandate(m_id)


# ── cancel_mandate (HITL I-27) ─────────────────────────────────────────────────


def test_cancel_mandate_returns_hitl_required(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    result = engine.cancel_mandate(m_id)
    assert result["status"] == "HITL_REQUIRED"


def test_cancel_mandate_returns_mandate_id(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    result = engine.cancel_mandate(m_id)
    assert result["mandate_id"] == m_id


def test_cancel_mandate_already_cancelled_raises(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    engine.confirm_cancel_mandate(m_id)
    with pytest.raises(ValueError, match="already cancelled"):
        engine.cancel_mandate(m_id)


def test_cancel_mandate_not_found_raises(engine: DirectDebitEngine) -> None:
    with pytest.raises(ValueError, match="not found"):
        engine.cancel_mandate("nonexistent")


# ── confirm_cancel_mandate ─────────────────────────────────────────────────────


def test_confirm_cancel_returns_cancelled(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    result = engine.confirm_cancel_mandate(m_id)
    assert result["status"] == "CANCELLED"


def test_confirm_cancel_sets_cancelled_at(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    result = engine.confirm_cancel_mandate(m_id)
    assert result["cancelled_at"] is not None


# ── collect ────────────────────────────────────────────────────────────────────


def test_collect_from_active_mandate(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    engine.authorise_mandate(m_id)
    engine.activate_mandate(m_id)
    result = engine.collect(m_id, Decimal("50.00"))
    assert result["status"] == "COLLECTED"


def test_collect_returns_dd_id(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    engine.authorise_mandate(m_id)
    engine.activate_mandate(m_id)
    result = engine.collect(m_id, Decimal("50.00"))
    assert result["dd_id"] != ""


def test_collect_non_active_mandate_raises(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    with pytest.raises(ValueError, match="not ACTIVE"):
        engine.collect(m_id, Decimal("50.00"))


def test_collect_zero_amount_raises(engine: DirectDebitEngine) -> None:
    m_id = _create_mandate(engine)
    engine.authorise_mandate(m_id)
    engine.activate_mandate(m_id)
    with pytest.raises(ValueError, match="must be positive"):
        engine.collect(m_id, Decimal("0"))


def test_collect_missing_mandate_raises(engine: DirectDebitEngine) -> None:
    with pytest.raises(ValueError, match="not found"):
        engine.collect("nonexistent", Decimal("50.00"))


# ── list_mandates ──────────────────────────────────────────────────────────────


def test_list_mandates_returns_count(engine: DirectDebitEngine) -> None:
    _create_mandate(engine, "cust-list")
    _create_mandate(engine, "cust-list")
    result = engine.list_mandates("cust-list")
    assert result["count"] == 2


def test_list_mandates_empty_for_new_customer(engine: DirectDebitEngine) -> None:
    result = engine.list_mandates("nobody")
    assert result["count"] == 0
