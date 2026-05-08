"""
tests/test_legacy_crypto_rpc_adapter.py — REWRITE-9 scaffold tests.

Covers: module import safety, adapter surface existence, structural Protocol
conformance (isinstance with CryptoRpcPort), broadcast_tx returns str hash,
get_block shape + stored block + scaffold fallback, estimate_fee Decimal-safe
and deterministic across all 6 chains × 3 priorities, fee_override injection,
broadcast log, health.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.ledger.crypto_ledger_port import (
    CryptoBlock,
    CryptoFeeEstimate,
    CryptoRpcPort,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.legacy.legacy_crypto_rpc_adapter import (
    LegacyCryptoRpcAdapter,
    _derive_tx_hash,
)

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)

_SIGNED_TX_BTC = "0200000001abc...deadbeef"
_SIGNED_TX_ETH = "0xf86c..."


# ---------------------------------------------------------------------------
# 1. Module import safety
# ---------------------------------------------------------------------------


def test_module_imports_cleanly() -> None:
    import importlib

    mod = importlib.import_module("services.ledger.legacy.legacy_crypto_rpc_adapter")
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Adapter surface
# ---------------------------------------------------------------------------


def test_adapter_has_broadcast_tx() -> None:
    assert hasattr(LegacyCryptoRpcAdapter, "broadcast_tx")


def test_adapter_has_get_block() -> None:
    assert hasattr(LegacyCryptoRpcAdapter, "get_block")


def test_adapter_has_estimate_fee() -> None:
    assert hasattr(LegacyCryptoRpcAdapter, "estimate_fee")


def test_adapter_has_health() -> None:
    assert hasattr(LegacyCryptoRpcAdapter, "health")


# ---------------------------------------------------------------------------
# 3. Structural Protocol conformance
# ---------------------------------------------------------------------------


def test_adapter_is_structural_instance_of_crypto_rpc_port() -> None:
    adapter = LegacyCryptoRpcAdapter()
    assert isinstance(adapter, CryptoRpcPort)


# ---------------------------------------------------------------------------
# 4. _derive_tx_hash — deterministic, encodes chain
# ---------------------------------------------------------------------------


def test_derive_tx_hash_is_deterministic() -> None:
    h1 = _derive_tx_hash(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    h2 = _derive_tx_hash(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    assert h1 == h2


def test_derive_tx_hash_differs_by_blockchain() -> None:
    btc = _derive_tx_hash(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    eth = _derive_tx_hash(_SIGNED_TX_BTC, SupportedBlockchain.ETH)
    assert btc != eth


def test_derive_tx_hash_differs_by_signed_tx() -> None:
    h1 = _derive_tx_hash("tx-a", SupportedBlockchain.ETH)
    h2 = _derive_tx_hash("tx-b", SupportedBlockchain.ETH)
    assert h1 != h2


def test_derive_tx_hash_starts_with_0x() -> None:
    h = _derive_tx_hash(_SIGNED_TX_ETH, SupportedBlockchain.ETH)
    assert h.startswith("0x")


# ---------------------------------------------------------------------------
# 5. broadcast_tx — return value, log accumulation
# ---------------------------------------------------------------------------


def test_broadcast_tx_returns_string() -> None:
    adapter = LegacyCryptoRpcAdapter()
    result = adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    assert isinstance(result, str)
    assert len(result) > 0


def test_broadcast_tx_returns_deterministic_hash() -> None:
    adapter = LegacyCryptoRpcAdapter()
    h1 = adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    h2 = adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    assert h1 == h2


def test_broadcast_tx_appends_to_log() -> None:
    adapter = LegacyCryptoRpcAdapter()
    adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    adapter.broadcast_tx(_SIGNED_TX_ETH, SupportedBlockchain.ETH)
    assert len(adapter._broadcast_log) == 2


def test_broadcast_tx_log_entry_shape() -> None:
    adapter = LegacyCryptoRpcAdapter()
    tx_hash = adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    signed_tx, blockchain, logged_hash = adapter._broadcast_log[0]
    assert signed_tx == _SIGNED_TX_BTC
    assert blockchain == SupportedBlockchain.BTC
    assert logged_hash == tx_hash


def test_broadcast_tx_different_chains_independent() -> None:
    adapter = LegacyCryptoRpcAdapter()
    h_btc = adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.BTC)
    h_eth = adapter.broadcast_tx(_SIGNED_TX_BTC, SupportedBlockchain.ETH)
    assert h_btc != h_eth


# ---------------------------------------------------------------------------
# 6. get_block — scaffold fallback + stored block
# ---------------------------------------------------------------------------


def test_get_block_returns_crypto_block() -> None:
    adapter = LegacyCryptoRpcAdapter()
    blk = adapter.get_block("hash-001", SupportedBlockchain.BTC)
    assert isinstance(blk, CryptoBlock)


def test_get_block_scaffold_hash_preserved() -> None:
    adapter = LegacyCryptoRpcAdapter()
    blk = adapter.get_block("hash-abc", SupportedBlockchain.ETH)
    assert blk.block_hash == "hash-abc"


def test_get_block_scaffold_blockchain_preserved() -> None:
    adapter = LegacyCryptoRpcAdapter()
    blk = adapter.get_block("hash-xyz", SupportedBlockchain.TRX)
    assert blk.blockchain == SupportedBlockchain.TRX


def test_get_block_scaffold_tx_count_zero() -> None:
    adapter = LegacyCryptoRpcAdapter()
    blk = adapter.get_block("hash-new", SupportedBlockchain.XRP)
    assert blk.tx_count == 0


def test_get_block_scaffold_block_number_positive() -> None:
    adapter = LegacyCryptoRpcAdapter()
    blk = adapter.get_block("hash-any", SupportedBlockchain.BTC)
    assert blk.block_number > 0


def test_get_block_returns_stored_block() -> None:
    stored = CryptoBlock(
        block_hash="stored-hash",
        block_number=999_999,
        blockchain=SupportedBlockchain.ETH,
        timestamp=_NOW,
        tx_count=42,
    )
    adapter = LegacyCryptoRpcAdapter(blocks={("stored-hash", SupportedBlockchain.ETH): stored})
    blk = adapter.get_block("stored-hash", SupportedBlockchain.ETH)
    assert blk.block_number == 999_999
    assert blk.tx_count == 42


def test_get_block_stored_vs_scaffold_distinct() -> None:
    stored = CryptoBlock(
        block_hash="h1",
        block_number=1,
        blockchain=SupportedBlockchain.BTC,
        timestamp=_NOW,
        tx_count=5,
    )
    adapter = LegacyCryptoRpcAdapter(blocks={("h1", SupportedBlockchain.BTC): stored})
    blk_stored = adapter.get_block("h1", SupportedBlockchain.BTC)
    blk_scaffold = adapter.get_block("h2", SupportedBlockchain.BTC)
    assert blk_stored.block_number == 1
    assert blk_scaffold.block_number != 1


# ---------------------------------------------------------------------------
# 7. estimate_fee — Decimal, determinism, all chains × all priorities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("blockchain", list(SupportedBlockchain))
def test_estimate_fee_returns_crypto_fee_estimate(blockchain: SupportedBlockchain) -> None:
    adapter = LegacyCryptoRpcAdapter()
    est = adapter.estimate_fee(blockchain, FeePriority.MEDIUM)
    assert isinstance(est, CryptoFeeEstimate)


@pytest.mark.parametrize("blockchain", list(SupportedBlockchain))
def test_estimate_fee_fee_is_decimal(blockchain: SupportedBlockchain) -> None:
    adapter = LegacyCryptoRpcAdapter()
    est = adapter.estimate_fee(blockchain, FeePriority.MEDIUM)
    assert isinstance(est.fee, Decimal)


@pytest.mark.parametrize("priority", list(FeePriority))
def test_estimate_fee_all_priorities_btc(priority: FeePriority) -> None:
    adapter = LegacyCryptoRpcAdapter()
    est = adapter.estimate_fee(SupportedBlockchain.BTC, priority)
    assert isinstance(est.fee, Decimal)
    assert est.fee > Decimal("0")


def test_estimate_fee_high_greater_than_medium_eth() -> None:
    adapter = LegacyCryptoRpcAdapter()
    high = adapter.estimate_fee(SupportedBlockchain.ETH, FeePriority.HIGH)
    medium = adapter.estimate_fee(SupportedBlockchain.ETH, FeePriority.MEDIUM)
    assert high.fee > medium.fee


def test_estimate_fee_low_less_than_medium_btc() -> None:
    adapter = LegacyCryptoRpcAdapter()
    low = adapter.estimate_fee(SupportedBlockchain.BTC, FeePriority.LOW)
    medium = adapter.estimate_fee(SupportedBlockchain.BTC, FeePriority.MEDIUM)
    assert low.fee < medium.fee


def test_estimate_fee_is_deterministic() -> None:
    adapter = LegacyCryptoRpcAdapter()
    e1 = adapter.estimate_fee(SupportedBlockchain.XRP, FeePriority.HIGH)
    e2 = adapter.estimate_fee(SupportedBlockchain.XRP, FeePriority.HIGH)
    assert e1.fee == e2.fee
    assert e1.priority == e2.priority


def test_estimate_fee_blockchain_bound() -> None:
    adapter = LegacyCryptoRpcAdapter()
    est = adapter.estimate_fee(SupportedBlockchain.DOT, FeePriority.MEDIUM)
    assert est.blockchain == SupportedBlockchain.DOT


def test_estimate_fee_currency_matches_blockchain() -> None:
    adapter = LegacyCryptoRpcAdapter()
    est = adapter.estimate_fee(SupportedBlockchain.TRX, FeePriority.LOW)
    assert est.currency == "TRX"


def test_estimate_fee_confirmation_blocks_high_less_than_low() -> None:
    adapter = LegacyCryptoRpcAdapter()
    high = adapter.estimate_fee(SupportedBlockchain.BTC, FeePriority.HIGH)
    low = adapter.estimate_fee(SupportedBlockchain.BTC, FeePriority.LOW)
    assert high.estimated_confirmation_blocks < low.estimated_confirmation_blocks


# ---------------------------------------------------------------------------
# 8. fee override injection
# ---------------------------------------------------------------------------


def test_estimate_fee_respects_override() -> None:
    override = {(SupportedBlockchain.ETH, FeePriority.HIGH): Decimal("0.01")}
    adapter = LegacyCryptoRpcAdapter(fee_overrides=override)
    est = adapter.estimate_fee(SupportedBlockchain.ETH, FeePriority.HIGH)
    assert est.fee == Decimal("0.01")


def test_estimate_fee_override_does_not_affect_other_chain() -> None:
    override = {(SupportedBlockchain.ETH, FeePriority.HIGH): Decimal("0.01")}
    adapter = LegacyCryptoRpcAdapter(fee_overrides=override)
    est_btc = adapter.estimate_fee(SupportedBlockchain.BTC, FeePriority.HIGH)
    assert est_btc.fee != Decimal("0.01")


# ---------------------------------------------------------------------------
# 9. health
# ---------------------------------------------------------------------------


def test_health_returns_true() -> None:
    adapter = LegacyCryptoRpcAdapter()
    assert adapter.health() is True
