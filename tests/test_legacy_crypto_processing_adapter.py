"""
tests/test_legacy_crypto_processing_adapter.py — REWRITE-8 scaffold tests.

Covers: module import safety, adapter surface existence, structural Protocol
conformance (method presence only — REWRITE-7 stubs raise NotImplementedError),
create_tx idempotency, Decimal invariant (I-01), fee estimation determinism,
explicit separation from REWRITE-7 wallet logic, no runtime side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.ledger.crypto_ledger_port import (
    CryptoFeeEstimate,
    CryptoLedgerPort,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoTransactionStatus,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.legacy.legacy_crypto_processing_adapter import (
    LegacyCryptoProcessingAdapter,
    compute_fee,
    fee_currency,
)

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)

_BTC_REQ = CryptoTransactionRequest(
    tx_id="tx-btc-001",
    from_wallet_id="w-btc",
    to_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf",
    blockchain=SupportedBlockchain.BTC,
    amount=Decimal("0.5"),
    currency="BTC",
    fee_level=FeePriority.MEDIUM,
    customer_id="cust-001",
)


# ---------------------------------------------------------------------------
# 1. Module import safety
# ---------------------------------------------------------------------------


def test_module_imports_cleanly() -> None:
    import importlib

    mod = importlib.import_module("services.ledger.legacy.legacy_crypto_processing_adapter")
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Adapter surface
# ---------------------------------------------------------------------------


def test_adapter_has_create_tx() -> None:
    assert hasattr(LegacyCryptoProcessingAdapter, "create_tx")


def test_adapter_has_get_fee_estimate() -> None:
    assert hasattr(LegacyCryptoProcessingAdapter, "get_fee_estimate")


def test_adapter_has_health() -> None:
    assert hasattr(LegacyCryptoProcessingAdapter, "health")


def test_adapter_has_get_balance_stub() -> None:
    assert hasattr(LegacyCryptoProcessingAdapter, "get_balance")


def test_adapter_has_create_wallet_address_stub() -> None:
    assert hasattr(LegacyCryptoProcessingAdapter, "create_wallet_address")


# ---------------------------------------------------------------------------
# 3. Structural Protocol conformance (method-presence check only)
#    Full behavioural conformance requires REWRITE-7 for wallet methods.
# ---------------------------------------------------------------------------


def test_adapter_is_structural_instance_of_crypto_ledger_port() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    assert isinstance(adapter, CryptoLedgerPort)


# ---------------------------------------------------------------------------
# 4. compute_fee — deterministic, Decimal-safe, all 6 chains × 3 priorities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("blockchain", list(SupportedBlockchain))
def test_compute_fee_returns_decimal(blockchain: SupportedBlockchain) -> None:
    fee = compute_fee(blockchain, FeePriority.MEDIUM)
    assert isinstance(fee, Decimal)


def test_compute_fee_high_greater_than_medium_btc() -> None:
    assert compute_fee(SupportedBlockchain.BTC, FeePriority.HIGH) > compute_fee(
        SupportedBlockchain.BTC, FeePriority.MEDIUM
    )


def test_compute_fee_low_less_than_medium_eth() -> None:
    assert compute_fee(SupportedBlockchain.ETH, FeePriority.LOW) < compute_fee(
        SupportedBlockchain.ETH, FeePriority.MEDIUM
    )


def test_compute_fee_is_deterministic() -> None:
    f1 = compute_fee(SupportedBlockchain.XRP, FeePriority.HIGH)
    f2 = compute_fee(SupportedBlockchain.XRP, FeePriority.HIGH)
    assert f1 == f2


# ---------------------------------------------------------------------------
# 5. fee_currency mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("blockchain", "expected"),
    [
        (SupportedBlockchain.BTC, "BTC"),
        (SupportedBlockchain.ETH, "ETH"),
        (SupportedBlockchain.TRX, "TRX"),
        (SupportedBlockchain.XRP, "XRP"),
        (SupportedBlockchain.DOT, "DOT"),
        (SupportedBlockchain.EOS, "EOS"),
    ],
)
def test_fee_currency_all_chains(blockchain: SupportedBlockchain, expected: str) -> None:
    assert fee_currency(blockchain) == expected


# ---------------------------------------------------------------------------
# 6. create_tx — result shape, Decimal invariant, PENDING status
# ---------------------------------------------------------------------------


def test_create_tx_returns_crypto_transaction_result() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert isinstance(result, CryptoTransactionResult)


def test_create_tx_preserves_tx_id() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert result.tx_id == "tx-btc-001"


def test_create_tx_starts_in_pending_state() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert result.status == CryptoTransactionStatus.PENDING


def test_create_tx_amount_is_decimal() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert isinstance(result.amount, Decimal)
    assert result.amount == Decimal("0.5")


def test_create_tx_fee_is_decimal() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert isinstance(result.fee, Decimal)


def test_create_tx_tx_hash_is_none_until_broadcast() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert result.tx_hash is None


def test_create_tx_blockchain_preserved() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert result.blockchain == SupportedBlockchain.BTC


def test_create_tx_confirmed_at_is_none() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    result = adapter.create_tx(_BTC_REQ)
    assert result.confirmed_at is None


# ---------------------------------------------------------------------------
# 7. create_tx idempotency (matches legacy tx-queue-fee-consumer dedup)
# ---------------------------------------------------------------------------


def test_create_tx_idempotent_same_tx_id() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    first = adapter.create_tx(_BTC_REQ)
    second = adapter.create_tx(_BTC_REQ)
    assert first is second


def test_create_tx_idempotent_returns_identical_result() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    first = adapter.create_tx(_BTC_REQ)
    second = adapter.create_tx(_BTC_REQ)
    assert first.tx_id == second.tx_id
    assert first.amount == second.amount
    assert first.fee == second.fee


def test_create_tx_different_tx_ids_are_independent() -> None:
    req2 = CryptoTransactionRequest(
        tx_id="tx-btc-002",
        from_wallet_id="w-btc",
        to_address="1A1z",
        blockchain=SupportedBlockchain.BTC,
        amount=Decimal("1.0"),
        currency="BTC",
        fee_level=FeePriority.HIGH,
        customer_id="cust-001",
    )
    adapter = LegacyCryptoProcessingAdapter()
    r1 = adapter.create_tx(_BTC_REQ)
    r2 = adapter.create_tx(req2)
    assert r1.tx_id != r2.tx_id
    assert r1 is not r2


# ---------------------------------------------------------------------------
# 8. create_tx fee override injection
# ---------------------------------------------------------------------------


def test_create_tx_respects_fee_override() -> None:
    override = {(SupportedBlockchain.BTC, FeePriority.MEDIUM): Decimal("0.0002")}
    adapter = LegacyCryptoProcessingAdapter(fee_overrides=override)
    result = adapter.create_tx(_BTC_REQ)
    assert result.fee == Decimal("0.0002")


# ---------------------------------------------------------------------------
# 9. get_fee_estimate — shape, Decimal, determinism
# ---------------------------------------------------------------------------


def test_get_fee_estimate_returns_crypto_fee_estimate() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    est = adapter.get_fee_estimate(SupportedBlockchain.ETH, Decimal("1.0"))
    assert isinstance(est, CryptoFeeEstimate)


def test_get_fee_estimate_fee_is_decimal() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    est = adapter.get_fee_estimate(SupportedBlockchain.BTC, Decimal("0.1"))
    assert isinstance(est.fee, Decimal)


def test_get_fee_estimate_blockchain_bound() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    est = adapter.get_fee_estimate(SupportedBlockchain.TRX, Decimal("100"))
    assert est.blockchain == SupportedBlockchain.TRX


def test_get_fee_estimate_currency_matches_blockchain() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    est = adapter.get_fee_estimate(SupportedBlockchain.DOT, Decimal("5"))
    assert est.currency == "DOT"


def test_get_fee_estimate_is_deterministic() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    e1 = adapter.get_fee_estimate(SupportedBlockchain.XRP, Decimal("1"))
    e2 = adapter.get_fee_estimate(SupportedBlockchain.XRP, Decimal("1"))
    assert e1.fee == e2.fee
    assert e1.priority == e2.priority


# ---------------------------------------------------------------------------
# 10. REWRITE-7 stubs — explicit delegation markers
# ---------------------------------------------------------------------------


def test_get_balance_raises_not_implemented() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    with pytest.raises(NotImplementedError):
        adapter.get_balance("w-001", SupportedBlockchain.BTC)


def test_create_wallet_address_raises_not_implemented() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    with pytest.raises(NotImplementedError):
        adapter.create_wallet_address("cust-001", SupportedBlockchain.ETH)


# ---------------------------------------------------------------------------
# 11. health
# ---------------------------------------------------------------------------


def test_health_returns_true() -> None:
    adapter = LegacyCryptoProcessingAdapter()
    assert adapter.health() is True
