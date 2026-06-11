from __future__ import annotations

from decimal import Decimal

import pytest

from services.treasury.nostro_recon_port import (
    InMemoryNOSTROReconPort,
    NostroBalance,
    NostroReconPortError,
)


def _bal(
    account_id: str = "ACCT-001",
    internal: str = "10000.00",
    external: str = "10000.00",
    as_of: str = "2026-06-09",
) -> NostroBalance:
    return NostroBalance(
        account_id=account_id,
        internal_gbp=Decimal(internal),
        external_gbp=Decimal(external),
        as_of=as_of,
    )


def _port(*balances: NostroBalance) -> InMemoryNOSTROReconPort:
    p = InMemoryNOSTROReconPort()
    for b in balances:
        p.seed(b)
    return p


async def test_get_nostro_balances_known_account() -> None:
    port = _port(_bal("ACCT-001", "5000.00", "5000.00"))
    result = await port.get_nostro_balances("ACCT-001", "2026-06-09")
    assert result.account_id == "ACCT-001"
    assert result.internal_gbp == Decimal("5000.00")


async def test_get_nostro_balances_unknown_raises() -> None:
    port = _port(_bal("ACCT-001"))
    with pytest.raises(NostroReconPortError, match="ACCT-999"):
        await port.get_nostro_balances("ACCT-999", "2026-06-09")


async def test_reconcile_matched_zero_difference() -> None:
    port = _port(_bal("ACCT-001", "10000.00", "10000.00"))
    result = await port.reconcile("ACCT-001", "2026-06-09")
    assert result.matched is True
    assert result.difference_gbp == Decimal("0")


async def test_reconcile_matched_within_tolerance() -> None:
    port = _port(_bal("ACCT-001", "10000.01", "10000.00"))
    result = await port.reconcile("ACCT-001", "2026-06-09")
    assert result.difference_gbp == Decimal("0.01")
    assert result.matched is True


async def test_reconcile_unmatched_exceeds_tolerance() -> None:
    port = _port(_bal("ACCT-001", "10000.02", "10000.00"))
    result = await port.reconcile("ACCT-001", "2026-06-09")
    assert result.difference_gbp == Decimal("0.02")
    assert result.matched is False


async def test_reconcile_large_discrepancy_unmatched() -> None:
    port = _port(_bal("ACCT-001", "15000.00", "10000.00"))
    result = await port.reconcile("ACCT-001", "2026-06-09")
    assert result.difference_gbp == Decimal("5000.00")
    assert result.matched is False


async def test_reconcile_negative_difference_matched() -> None:
    port = _port(_bal("ACCT-001", "9999.99", "10000.00"))
    result = await port.reconcile("ACCT-001", "2026-06-09")
    assert result.difference_gbp == Decimal("-0.01")
    assert result.matched is True


async def test_reconcile_unknown_account_raises() -> None:
    port = InMemoryNOSTROReconPort()
    with pytest.raises(NostroReconPortError):
        await port.reconcile("MISSING", "2026-06-09")


async def test_result_carries_as_of_from_balance() -> None:
    port = _port(_bal("ACCT-001", as_of="2026-05-31"))
    result = await port.reconcile("ACCT-001", "2026-06-09")
    assert result.as_of == "2026-05-31"
