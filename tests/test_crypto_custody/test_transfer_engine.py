"""
tests/test_crypto_custody/test_transfer_engine.py — Tests for TransferEngine
IL-CDC-01 | Phase 35 | 20 tests
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.crypto_custody.crypto_agent import HITLProposal
from services.crypto_custody.models import (
    AssetType,
    InMemoryAuditStore,
    InMemoryTransferStore,
    InMemoryWalletStore,
    TransferStatus,
)
from services.crypto_custody.transfer_engine import TransferEngine


@pytest.fixture()
def engine():
    wallet_store = InMemoryWalletStore()
    transfer_store = InMemoryTransferStore()
    audit = InMemoryAuditStore()
    return TransferEngine(
        transfer_port=transfer_store,
        wallet_port=wallet_store,
        audit_port=audit,
    )


def test_initiate_transfer_returns_pending(engine):
    t = engine.initiate_transfer(
        "wallet-btc-001", "1addr123456789012345678901", Decimal("0.001"), AssetType.BTC
    )
    assert t.status == TransferStatus.PENDING


def test_initiate_transfer_amount_decimal(engine):
    t = engine.initiate_transfer("wallet-eth-001", "0x" + "a" * 40, Decimal("0.5"), AssetType.ETH)
    assert type(t.amount) is Decimal


def test_initiate_transfer_stores_record(engine):
    t = engine.initiate_transfer(
        "wallet-btc-001", "1addr123456789012345678901", Decimal("0.1"), AssetType.BTC
    )
    found = engine._transfers.get_transfer(t.id)
    assert found is not None


def test_initiate_transfer_zero_amount_raises(engine):
    with pytest.raises(ValueError):
        engine.initiate_transfer("wallet-btc-001", "addr", Decimal("0"), AssetType.BTC)


def test_initiate_transfer_negative_amount_raises(engine):
    with pytest.raises(ValueError):
        engine.initiate_transfer("wallet-btc-001", "addr", Decimal("-1"), AssetType.BTC)


def test_initiate_transfer_wallet_not_found_raises(engine):
    with pytest.raises(ValueError, match="not found"):
        engine.initiate_transfer("wallet-nonexistent", "addr", Decimal("0.1"), AssetType.BTC)


def test_validate_address_btc_valid(engine):
    assert engine.validate_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7Divfxx", AssetType.BTC) is True


def test_validate_address_btc_too_short(engine):
    assert engine.validate_address("1abc", AssetType.BTC) is False


def test_validate_address_eth_valid(engine):
    assert engine.validate_address("0x" + "a" * 40, AssetType.ETH) is True


def test_validate_address_eth_wrong_prefix(engine):
    assert engine.validate_address("x" * 42, AssetType.ETH) is False


def test_validate_address_usdt_valid(engine):
    assert engine.validate_address("0x" + "b" * 40, AssetType.USDT) is True


def test_execute_transfer_small_amount_returns_record(engine):
    t = engine.initiate_transfer(
        "wallet-btc-001", "1addr123456789012345678901", Decimal("0.001"), AssetType.BTC
    )
    result = engine.execute_transfer(t.id)
    assert not isinstance(result, HITLProposal)
    assert result.status == TransferStatus.EXECUTING


def test_execute_transfer_large_returns_hitl(engine):
    t = engine.initiate_transfer("wallet-eth-001", "0x" + "c" * 40, Decimal("1000"), AssetType.ETH)
    result = engine.execute_transfer(t.id)
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_execute_transfer_at_threshold_returns_hitl(engine):
    t = engine.initiate_transfer("wallet-eth-001", "0x" + "d" * 40, Decimal("1000"), AssetType.ETH)
    result = engine.execute_transfer(t.id)
    assert isinstance(result, HITLProposal)


def test_execute_transfer_not_found_raises(engine):
    with pytest.raises(ValueError):
        engine.execute_transfer("txfr-nonexistent")


def test_confirm_on_chain_sets_confirmed(engine):
    t = engine.initiate_transfer(
        "wallet-btc-001", "1addr123456789012345678901", Decimal("0.001"), AssetType.BTC
    )
    confirmed = engine.confirm_on_chain(t.id, "0xabc123txhash")
    assert confirmed.status == TransferStatus.CONFIRMED
    assert confirmed.txhash == "0xabc123txhash"


def test_reject_transfer_sets_rejected(engine):
    t = engine.initiate_transfer(
        "wallet-btc-001", "1addr123456789012345678901", Decimal("0.001"), AssetType.BTC
    )
    rejected = engine.reject_transfer(t.id, "compliance block")
    assert rejected.status == TransferStatus.REJECTED


def test_reject_transfer_not_found_raises(engine):
    with pytest.raises(ValueError):
        engine.reject_transfer("txfr-nonexistent", "reason")


def test_travel_rule_required_for_large_transfer(engine):
    t = engine.initiate_transfer("wallet-eth-001", "0x" + "e" * 40, Decimal("1000"), AssetType.ETH)
    assert t.travel_rule_required is True


def test_travel_rule_not_required_for_small_transfer(engine):
    t = engine.initiate_transfer(
        "wallet-btc-001", "1addr123456789012345678901", Decimal("0.001"), AssetType.BTC
    )
    assert t.travel_rule_required is False
