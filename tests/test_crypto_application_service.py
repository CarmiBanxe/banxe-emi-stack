"""
tests/test_crypto_application_service.py — CryptoApplicationService routing tests.

Verifies that each method delegates to the correct underlying adapter
(REWRITE-7 wallet / REWRITE-8 processing / REWRITE-9 rpc) and that
cross-delegation is never invoked via this service.

No mocking — uses real scaffold adapters. Isolation guaranteed by
REWRITE-7/8 NotImplementedError stubs for cross-adapter methods.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.ledger.crypto_application_service import CryptoApplicationService
from services.ledger.crypto_ledger_port import (
    CryptoBlock,
    CryptoTransactionRequest,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.legacy.legacy_crypto_processing_adapter import (
    LegacyCryptoProcessingAdapter,
)
from services.ledger.legacy.legacy_crypto_rpc_adapter import LegacyCryptoRpcAdapter
from services.ledger.legacy.legacy_crypto_wallet_adapter import LegacyCryptoWalletAdapter

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)

_BTC_REQ = CryptoTransactionRequest(
    tx_id="svc-tx-001",
    from_wallet_id="w-btc",
    to_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf",
    blockchain=SupportedBlockchain.BTC,
    amount=Decimal("0.1"),
    currency="BTC",
    fee_level=FeePriority.MEDIUM,
    customer_id="cust-svc-01",
)


def _make_svc() -> CryptoApplicationService:
    return CryptoApplicationService(
        wallet=LegacyCryptoWalletAdapter(),
        processing=LegacyCryptoProcessingAdapter(),
        rpc=LegacyCryptoRpcAdapter(),
    )


# ---------------------------------------------------------------------------
# 1. Module import safety
# ---------------------------------------------------------------------------


def test_module_imports_cleanly() -> None:
    import importlib

    mod = importlib.import_module("services.ledger.crypto_application_service")
    assert mod is not None


def test_service_instantiates() -> None:
    svc = _make_svc()
    assert svc is not None


# ---------------------------------------------------------------------------
# 2. Constructor DI stores adapters
# ---------------------------------------------------------------------------


def test_service_stores_wallet_adapter() -> None:
    wallet = LegacyCryptoWalletAdapter()
    svc = CryptoApplicationService(
        wallet=wallet,
        processing=LegacyCryptoProcessingAdapter(),
        rpc=LegacyCryptoRpcAdapter(),
    )
    assert svc._wallet is wallet


def test_service_stores_processing_adapter() -> None:
    processing = LegacyCryptoProcessingAdapter()
    svc = CryptoApplicationService(
        wallet=LegacyCryptoWalletAdapter(),
        processing=processing,
        rpc=LegacyCryptoRpcAdapter(),
    )
    assert svc._processing is processing


def test_service_stores_rpc_adapter() -> None:
    rpc = LegacyCryptoRpcAdapter()
    svc = CryptoApplicationService(
        wallet=LegacyCryptoWalletAdapter(),
        processing=LegacyCryptoProcessingAdapter(),
        rpc=rpc,
    )
    assert svc._rpc is rpc


# ---------------------------------------------------------------------------
# 3. get_balance → wallet adapter
# ---------------------------------------------------------------------------


def test_get_balance_delegates_to_wallet() -> None:
    svc = _make_svc()
    bal = svc.get_balance("w-eth", SupportedBlockchain.ETH)
    assert bal.wallet_id == "w-eth"
    assert bal.blockchain == SupportedBlockchain.ETH
    assert isinstance(bal.confirmed_balance, Decimal)


def test_get_balance_default_is_zero() -> None:
    svc = _make_svc()
    bal = svc.get_balance("w-unknown", SupportedBlockchain.BTC)
    assert bal.confirmed_balance == Decimal("0")


# ---------------------------------------------------------------------------
# 4. create_wallet_address → wallet adapter
# ---------------------------------------------------------------------------


def test_create_wallet_address_delegates_to_wallet() -> None:
    svc = _make_svc()
    addr = svc.create_wallet_address("cust-001", SupportedBlockchain.ETH)
    assert addr.customer_id == "cust-001"
    assert addr.blockchain == SupportedBlockchain.ETH
    assert addr.address.startswith("addr-ETH-")


# ---------------------------------------------------------------------------
# 5. create_tx → processing adapter (NOT wallet)
# ---------------------------------------------------------------------------


def test_create_tx_delegates_to_processing() -> None:
    svc = _make_svc()
    result = svc.create_tx(_BTC_REQ)
    assert result.tx_id == "svc-tx-001"
    assert isinstance(result.fee, Decimal)


def test_create_tx_is_idempotent_through_service() -> None:
    svc = _make_svc()
    r1 = svc.create_tx(_BTC_REQ)
    r2 = svc.create_tx(_BTC_REQ)
    assert r1 is r2


def test_create_tx_not_via_wallet_adapter() -> None:
    """Ensures wallet adapter is NOT used for create_tx (it would raise NIE)."""
    svc = _make_svc()
    result = svc.create_tx(_BTC_REQ)
    assert result is not None  # if delegated to wallet: NotImplementedError


# ---------------------------------------------------------------------------
# 6. get_fee_estimate → processing adapter (NOT wallet)
# ---------------------------------------------------------------------------


def test_get_fee_estimate_delegates_to_processing() -> None:
    svc = _make_svc()
    est = svc.get_fee_estimate(SupportedBlockchain.ETH, Decimal("1.0"))
    assert est.blockchain == SupportedBlockchain.ETH
    assert isinstance(est.fee, Decimal)
    assert est.fee > Decimal("0")


def test_get_fee_estimate_not_via_wallet_adapter() -> None:
    svc = _make_svc()
    est = svc.get_fee_estimate(SupportedBlockchain.BTC, Decimal("0.5"))
    assert est is not None  # if delegated to wallet: NotImplementedError


# ---------------------------------------------------------------------------
# 7. broadcast_tx → rpc adapter
# ---------------------------------------------------------------------------


def test_broadcast_tx_delegates_to_rpc() -> None:
    svc = _make_svc()
    tx_hash = svc.broadcast_tx("0xdeadbeef", SupportedBlockchain.ETH)
    assert tx_hash.startswith("0x")
    assert len(tx_hash) > 10


def test_broadcast_tx_is_deterministic() -> None:
    svc = _make_svc()
    h1 = svc.broadcast_tx("signed-tx-abc", SupportedBlockchain.BTC)
    h2 = svc.broadcast_tx("signed-tx-abc", SupportedBlockchain.BTC)
    assert h1 == h2


# ---------------------------------------------------------------------------
# 8. get_block → rpc adapter
# ---------------------------------------------------------------------------


def test_get_block_delegates_to_rpc() -> None:
    svc = _make_svc()
    blk = svc.get_block("block-hash-001", SupportedBlockchain.BTC)
    assert isinstance(blk, CryptoBlock)
    assert blk.block_hash == "block-hash-001"


def test_get_block_with_stored_block() -> None:
    stored = CryptoBlock(
        block_hash="stored-blk",
        block_number=1_000_000,
        blockchain=SupportedBlockchain.ETH,
        timestamp=_NOW,
        tx_count=10,
    )
    rpc = LegacyCryptoRpcAdapter(blocks={("stored-blk", SupportedBlockchain.ETH): stored})
    svc = CryptoApplicationService(
        wallet=LegacyCryptoWalletAdapter(),
        processing=LegacyCryptoProcessingAdapter(),
        rpc=rpc,
    )
    blk = svc.get_block("stored-blk", SupportedBlockchain.ETH)
    assert blk.block_number == 1_000_000
    assert blk.tx_count == 10


# ---------------------------------------------------------------------------
# 9. estimate_fee → rpc adapter
# ---------------------------------------------------------------------------


def test_estimate_fee_delegates_to_rpc() -> None:
    svc = _make_svc()
    est = svc.estimate_fee(SupportedBlockchain.BTC, FeePriority.HIGH)
    assert isinstance(est.fee, Decimal)
    assert est.priority == FeePriority.HIGH


def test_estimate_fee_high_greater_than_low() -> None:
    svc = _make_svc()
    high = svc.estimate_fee(SupportedBlockchain.ETH, FeePriority.HIGH)
    low = svc.estimate_fee(SupportedBlockchain.ETH, FeePriority.LOW)
    assert high.fee > low.fee


# ---------------------------------------------------------------------------
# 10. health — all three adapters
# ---------------------------------------------------------------------------


def test_health_returns_dict() -> None:
    svc = _make_svc()
    result = svc.health()
    assert isinstance(result, dict)


def test_health_has_all_three_keys() -> None:
    svc = _make_svc()
    result = svc.health()
    assert set(result.keys()) == {"wallet", "processing", "rpc"}


def test_health_all_true_for_scaffold_adapters() -> None:
    svc = _make_svc()
    result = svc.health()
    assert result["wallet"] is True
    assert result["processing"] is True
    assert result["rpc"] is True
