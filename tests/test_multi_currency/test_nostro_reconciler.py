"""tests/test_multi_currency/test_nostro_reconciler.py — NostroReconciler tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.multi_currency.models import (
    InMemoryMCAudit,
    InMemoryNostroStore,
    ReconciliationStatus,
)
from services.multi_currency.nostro_reconciler import _TOLERANCE, NostroReconciler


def _make_reconciler() -> NostroReconciler:
    return NostroReconciler(
        nostro_store=InMemoryNostroStore(),
        audit=InMemoryMCAudit(),
    )


# ── Tolerance constant ─────────────────────────────────────────────────────────


def test_tolerance_is_one_gbp() -> None:
    assert Decimal("1.00") == _TOLERANCE


# ── reconcile — MATCHED cases ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_exact_match_is_matched() -> None:
    rec = _make_reconciler()
    result = await rec.reconcile("nostro-gbp-001", Decimal("5000000"))
    assert result.status == ReconciliationStatus.MATCHED
    assert result.variance == Decimal("0")


@pytest.mark.asyncio
async def test_reconcile_within_tolerance_positive_is_matched() -> None:
    rec = _make_reconciler()
    # their_balance = our_balance - 0.50 (variance = 0.50 <= 1.00)
    result = await rec.reconcile("nostro-gbp-001", Decimal("4999999.50"))
    assert result.status == ReconciliationStatus.MATCHED


@pytest.mark.asyncio
async def test_reconcile_within_tolerance_negative_is_matched() -> None:
    rec = _make_reconciler()
    # their_balance = our_balance + 0.99 (variance = -0.99, abs = 0.99 <= 1.00)
    result = await rec.reconcile("nostro-gbp-001", Decimal("5000000.99"))
    assert result.status == ReconciliationStatus.MATCHED


@pytest.mark.asyncio
async def test_reconcile_exactly_at_tolerance_boundary_is_matched() -> None:
    rec = _make_reconciler()
    # variance exactly = 1.00 → MATCHED (<=)
    result = await rec.reconcile("nostro-gbp-001", Decimal("4999999.00"))
    assert result.status == ReconciliationStatus.MATCHED


# ── reconcile — DISCREPANCY cases ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_above_tolerance_is_discrepancy() -> None:
    rec = _make_reconciler()
    # their_balance = 4999998.99 → variance = 1.01 > 1.00
    result = await rec.reconcile("nostro-gbp-001", Decimal("4999998.99"))
    assert result.status == ReconciliationStatus.DISCREPANCY


@pytest.mark.asyncio
async def test_reconcile_large_discrepancy_is_discrepancy() -> None:
    rec = _make_reconciler()
    result = await rec.reconcile("nostro-gbp-001", Decimal("4000000"))
    assert result.status == ReconciliationStatus.DISCREPANCY
    assert result.variance == Decimal("1000000")


@pytest.mark.asyncio
async def test_reconcile_eur_nostro() -> None:
    rec = _make_reconciler()
    result = await rec.reconcile("nostro-eur-001", Decimal("3000000"))
    assert result.status == ReconciliationStatus.MATCHED


# ── reconcile — return fields ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_returns_our_balance() -> None:
    rec = _make_reconciler()
    result = await rec.reconcile("nostro-gbp-001", Decimal("5000000"))
    assert result.our_balance == Decimal("5000000")


@pytest.mark.asyncio
async def test_reconcile_returns_their_balance() -> None:
    rec = _make_reconciler()
    result = await rec.reconcile("nostro-gbp-001", Decimal("4999999"))
    assert result.their_balance == Decimal("4999999")


@pytest.mark.asyncio
async def test_reconcile_unknown_nostro_raises() -> None:
    rec = _make_reconciler()
    with pytest.raises(ValueError, match="Nostro account not found"):
        await rec.reconcile("nonexistent-nostro", Decimal("100"))


# ── list_nostros / get_nostro ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_nostros_returns_seeded_accounts() -> None:
    rec = _make_reconciler()
    nostros = await rec.list_nostros()
    assert len(nostros) == 2


@pytest.mark.asyncio
async def test_get_nostro_returns_seeded_account() -> None:
    rec = _make_reconciler()
    nostro = await rec.get_nostro("nostro-gbp-001")
    assert nostro is not None
    assert nostro.bank_name == "Barclays"


@pytest.mark.asyncio
async def test_get_nostro_returns_none_for_unknown() -> None:
    rec = _make_reconciler()
    nostro = await rec.get_nostro("does-not-exist")
    assert nostro is None


# ── update_our_balance ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_our_balance_updates_correctly() -> None:
    rec = _make_reconciler()
    updated = await rec.update_our_balance("nostro-gbp-001", Decimal("6000000"))
    assert updated.our_balance == Decimal("6000000")


@pytest.mark.asyncio
async def test_update_our_balance_unknown_raises() -> None:
    rec = _make_reconciler()
    with pytest.raises(ValueError, match="Nostro account not found"):
        await rec.update_our_balance("nonexistent", Decimal("100"))
