"""
tests/test_crypto_custody/test_wallet_manager.py — Tests for WalletManager
IL-CDC-01 | Phase 35 | 20 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.crypto_custody.models import (
    AssetType,
    InMemoryAuditStore,
    InMemoryWalletStore,
    NetworkType,
    WalletStatus,
)
from services.crypto_custody.wallet_manager import WalletManager


@pytest.fixture()
def store():
    return InMemoryWalletStore()


@pytest.fixture()
def audit():
    return InMemoryAuditStore()


@pytest.fixture()
def wm(store, audit):
    return WalletManager(wallet_port=store, audit_port=audit)


def test_create_wallet_returns_record(wm):
    w = wm.create_wallet("owner-1", AssetType.ETH, "HOT", NetworkType.MAINNET)
    assert w.owner_id == "owner-1"
    assert w.asset_type == AssetType.ETH
    assert w.status == WalletStatus.ACTIVE
    assert w.balance == Decimal("0")


def test_create_wallet_btc_address_format(wm):
    w = wm.create_wallet("owner-1", AssetType.BTC, "HOT", NetworkType.MAINNET)
    assert w.address.startswith("1")


def test_create_wallet_eth_address_format(wm):
    w = wm.create_wallet("owner-1", AssetType.ETH, "HOT", NetworkType.MAINNET)
    assert w.address.startswith("0x")


def test_create_wallet_usdt_address_eth_like(wm):
    w = wm.create_wallet("owner-1", AssetType.USDT, "COLD", NetworkType.MAINNET)
    assert w.address.startswith("0x")


def test_create_wallet_deterministic_address(wm):
    w1 = wm.create_wallet("owner-same", AssetType.ETH, "HOT", NetworkType.MAINNET)
    w2 = wm.create_wallet("owner-same", AssetType.ETH, "HOT", NetworkType.MAINNET)
    assert w1.address == w2.address


def test_create_wallet_invalid_type_raises(wm):
    with pytest.raises(ValueError, match="Invalid wallet_type"):
        wm.create_wallet("owner-1", AssetType.BTC, "INVALID", NetworkType.MAINNET)


def test_get_balance_seeded_btc(wm):
    balance = wm.get_balance("wallet-btc-001")
    assert isinstance(balance, Decimal)
    assert balance == Decimal("0.50000000")


def test_get_balance_seeded_eth(wm):
    balance = wm.get_balance("wallet-eth-001")
    assert balance == Decimal("2.50000000")


def test_get_balance_not_found_raises(wm):
    with pytest.raises(ValueError, match="not found"):
        wm.get_balance("wallet-nonexistent")


def test_get_balance_returns_decimal_not_float(wm):
    balance = wm.get_balance("wallet-btc-001")
    assert type(balance) is Decimal


def test_list_wallets_owner_001(wm):
    wallets = wm.list_wallets("owner-001")
    assert len(wallets) == 3


def test_list_wallets_unknown_owner_empty(wm):
    wallets = wm.list_wallets("owner-xyz")
    assert wallets == []


def test_list_wallets_new_owner_after_create(wm):
    wm.create_wallet("new-owner", AssetType.SOL, "HOT", NetworkType.MAINNET)
    wallets = wm.list_wallets("new-owner")
    assert len(wallets) == 1


def test_archive_wallet_returns_hitl(wm):
    proposal = wm.archive_wallet("wallet-btc-001")
    assert proposal.autonomy_level == "L4"
    assert "ARCHIVE" in proposal.action


def test_archive_wallet_not_found_raises(wm):
    with pytest.raises(ValueError, match="not found"):
        wm.archive_wallet("wallet-nonexistent")


def test_archive_wallet_requires_compliance_officer(wm):
    proposal = wm.archive_wallet("wallet-eth-001")
    assert "Compliance" in proposal.requires_approval_from


def test_create_wallet_audit_logged(wm, audit):
    wm.create_wallet("owner-audit", AssetType.XRP, "HOT", NetworkType.MAINNET)
    records = audit.get_records()
    assert any(r["action"] == "CREATE_WALLET" for r in records)


def test_archive_wallet_audit_logged(wm, audit):
    wm.archive_wallet("wallet-btc-001")
    records = audit.get_records()
    assert any(r["action"] == "ARCHIVE_WALLET" for r in records)


def test_create_multiple_wallets_different_ids(wm):
    w1 = wm.create_wallet("owner-2", AssetType.BTC, "HOT", NetworkType.MAINNET)
    w2 = wm.create_wallet("owner-2", AssetType.ETH, "HOT", NetworkType.MAINNET)
    assert w1.id != w2.id


def test_create_wallet_testnet(wm):
    w = wm.create_wallet("owner-test", AssetType.ETH, "HOT", NetworkType.TESTNET)
    assert w.network == NetworkType.TESTNET
