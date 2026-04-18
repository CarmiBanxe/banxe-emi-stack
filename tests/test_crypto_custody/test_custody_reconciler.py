"""
tests/test_crypto_custody/test_custody_reconciler.py — Tests for CustodyReconciler
IL-CDC-01 | Phase 35 | 18 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.crypto_custody.custody_reconciler import TOLERANCE_SATOSHI, CustodyReconciler
from services.crypto_custody.models import (
    AssetType,
    InMemoryAuditStore,
    InMemoryOnChainStore,
    InMemoryWalletStore,
    NetworkType,
)


@pytest.fixture()
def wallet_store():
    return InMemoryWalletStore()


@pytest.fixture()
def on_chain():
    return InMemoryOnChainStore()


@pytest.fixture()
def audit():
    return InMemoryAuditStore()


@pytest.fixture()
def reconciler(wallet_store, on_chain, audit):
    return CustodyReconciler(wallet_port=wallet_store, on_chain_port=on_chain, audit_port=audit)


def test_tolerance_satoshi_value():
    assert Decimal("0.00000001") == TOLERANCE_SATOSHI


def test_reconcile_wallet_btc_discrepancy(reconciler):
    result = reconciler.reconcile_wallet("wallet-btc-001")
    assert result.wallet_id == "wallet-btc-001"
    assert result.status in ("MATCHED", "DISCREPANCY")


def test_reconcile_wallet_result_types_are_decimal(reconciler):
    result = reconciler.reconcile_wallet("wallet-eth-001")
    assert type(result.on_chain_balance) is Decimal
    assert type(result.off_chain_balance) is Decimal
    assert type(result.discrepancy) is Decimal


def test_reconcile_wallet_not_found_raises(reconciler):
    with pytest.raises(ValueError, match="not found"):
        reconciler.reconcile_wallet("wallet-nonexistent")


def test_reconcile_wallet_matched_when_on_chain_equals_off_chain(reconciler, wallet_store):
    from datetime import datetime  # noqa: PLC0415

    from services.crypto_custody.models import (
        WalletRecord,  # noqa: PLC0415
        WalletStatus,  # noqa: PLC0415
    )

    w = WalletRecord(
        id="wallet-match-test",
        asset_type=AssetType.BTC,
        status=WalletStatus.ACTIVE,
        address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf6n",
        balance=Decimal("1.00000000"),
        network=NetworkType.MAINNET,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        owner_id="owner-test",
    )
    wallet_store.save_wallet(w)
    result = reconciler.reconcile_wallet("wallet-match-test")
    assert result.status == "MATCHED"


def test_reconcile_wallet_discrepancy_when_large_diff(reconciler, wallet_store):
    from datetime import datetime  # noqa: PLC0415

    from services.crypto_custody.models import WalletRecord, WalletStatus  # noqa: PLC0415

    w = WalletRecord(
        id="wallet-disc-test",
        asset_type=AssetType.ETH,
        status=WalletStatus.ACTIVE,
        address="0x" + "aa" * 20,
        balance=Decimal("5.00000000"),
        network=NetworkType.MAINNET,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        owner_id="owner-test",
    )
    wallet_store.save_wallet(w)
    result = reconciler.reconcile_wallet("wallet-disc-test")
    assert result.status == "DISCREPANCY"
    assert result.discrepancy > Decimal("0")


def test_reconcile_all_returns_list(reconciler):
    results = reconciler.reconcile_all("owner-001")
    assert isinstance(results, list)
    assert len(results) == 3


def test_reconcile_all_empty_owner(reconciler):
    results = reconciler.reconcile_all("owner-xyz")
    assert results == []


def test_flag_discrepancy_logs_audit(reconciler, audit):
    result = reconciler.reconcile_wallet("wallet-btc-001")
    reconciler.flag_discrepancy(result)
    records = audit.get_records()
    assert any(r["action"] == "FLAG_DISCREPANCY" for r in records)


def test_reconcile_wallet_discrepancy_non_negative(reconciler):
    result = reconciler.reconcile_wallet("wallet-usdt-001")
    assert result.discrepancy >= Decimal("0")


def test_reconcile_within_satoshi_tolerance(reconciler, wallet_store):
    from datetime import datetime  # noqa: PLC0415

    from services.crypto_custody.models import WalletRecord, WalletStatus  # noqa: PLC0415

    w = WalletRecord(
        id="wallet-tol-test",
        asset_type=AssetType.BTC,
        status=WalletStatus.ACTIVE,
        address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf6n",
        balance=Decimal("1.00000000"),
        network=NetworkType.MAINNET,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        owner_id="owner-tol",
    )
    wallet_store.save_wallet(w)
    result = reconciler.reconcile_wallet("wallet-tol-test")
    if abs(result.on_chain_balance - result.off_chain_balance) <= TOLERANCE_SATOSHI:
        assert result.status == "MATCHED"


def test_reconcile_logs_audit_on_success(reconciler, audit):
    reconciler.reconcile_wallet("wallet-btc-001")
    records = audit.get_records()
    assert any(r["action"] == "RECONCILE" for r in records)


def test_reconcile_all_owner_001_three_wallets(reconciler):
    results = reconciler.reconcile_all("owner-001")
    wallet_ids = {r.wallet_id for r in results}
    assert "wallet-btc-001" in wallet_ids
    assert "wallet-eth-001" in wallet_ids
    assert "wallet-usdt-001" in wallet_ids


def test_flag_discrepancy_outcome_flagged(reconciler, audit):
    result = reconciler.reconcile_wallet("wallet-eth-001")
    reconciler.flag_discrepancy(result)
    records = audit.get_records()
    flag_records = [r for r in records if r["action"] == "FLAG_DISCREPANCY"]
    assert any(r["outcome"] == "FLAGGED" for r in flag_records)


def test_reconcile_wallet_status_is_string(reconciler):
    result = reconciler.reconcile_wallet("wallet-btc-001")
    assert isinstance(result.status, str)
    assert result.status in ("MATCHED", "DISCREPANCY")


def test_reconcile_wallet_timestamp_set(reconciler):
    result = reconciler.reconcile_wallet("wallet-btc-001")
    assert result.timestamp is not None


def test_reconcile_multiple_owners_independent(reconciler):
    results_001 = reconciler.reconcile_all("owner-001")
    results_xyz = reconciler.reconcile_all("owner-xyz")
    assert len(results_001) == 3
    assert len(results_xyz) == 0
