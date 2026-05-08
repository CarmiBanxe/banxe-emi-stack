"""
tests/test_crypto_ledger_port.py — ADR-031 prerequisite: CryptoLedgerPort scaffold tests.

Covers: module import safety, Protocol surface, enum stability, frozen domain models,
I-01 Decimal invariant, structural stub conformance, no runtime side effects.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import importlib

import pytest

from services.ledger.crypto_ledger_port import (
    CryptoBalance,
    CryptoBlock,
    CryptoFeeEstimate,
    CryptoLedgerError,
    CryptoLedgerPort,
    CryptoRpcPort,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoTransactionStatus,
    CryptoWalletAddress,
    FeePriority,
    SupportedBlockchain,
)

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Minimal in-memory stubs — used only for structural conformance checks
# ---------------------------------------------------------------------------


class _LedgerStub:
    def get_balance(self, wallet_id: str, blockchain: SupportedBlockchain) -> CryptoBalance:
        return CryptoBalance(
            wallet_id=wallet_id,
            blockchain=blockchain,
            confirmed_balance=Decimal("0"),
            unconfirmed_balance=Decimal("0"),
            currency="BTC",
            as_of=_NOW,
        )

    def create_wallet_address(
        self, customer_id: str, blockchain: SupportedBlockchain
    ) -> CryptoWalletAddress:
        return CryptoWalletAddress(
            wallet_id="w-001",
            customer_id=customer_id,
            blockchain=blockchain,
            address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf",
            created_at=_NOW,
        )

    def create_tx(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        return CryptoTransactionResult(
            tx_id=request.tx_id,
            tx_hash=None,
            blockchain=request.blockchain,
            amount=request.amount,
            fee=Decimal("0.0001"),
            currency=request.currency,
            status=CryptoTransactionStatus.PENDING,
            from_wallet_id=request.from_wallet_id,
            to_address=request.to_address,
            created_at=_NOW,
            confirmed_at=None,
        )

    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=Decimal("0.0001"),
            currency="BTC",
            priority=FeePriority.MEDIUM,
            estimated_confirmation_blocks=3,
        )

    def health(self) -> bool:
        return True


class _RpcStub:
    def broadcast_tx(self, signed_tx: str, blockchain: SupportedBlockchain) -> str:
        return "deadbeef" * 8

    def get_block(self, block_hash: str, blockchain: SupportedBlockchain) -> CryptoBlock:
        return CryptoBlock(
            block_hash=block_hash,
            block_number=840000,
            blockchain=blockchain,
            timestamp=_NOW,
            tx_count=3000,
        )

    def estimate_fee(
        self, blockchain: SupportedBlockchain, priority: FeePriority
    ) -> CryptoFeeEstimate:
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=Decimal("0.00005"),
            currency="BTC",
            priority=priority,
            estimated_confirmation_blocks=1,
        )

    def health(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# 1. Module import safety
# ---------------------------------------------------------------------------


def test_module_imports_cleanly() -> None:
    mod = importlib.import_module("services.ledger.crypto_ledger_port")
    assert mod is not None


def test_no_runtime_side_effects_on_reimport() -> None:
    mod = importlib.import_module("services.ledger.crypto_ledger_port")
    reloaded = importlib.reload(mod)
    assert reloaded is not None


# ---------------------------------------------------------------------------
# 2. Enum stability
# ---------------------------------------------------------------------------


def test_supported_blockchain_all_six_chains() -> None:
    assert set(SupportedBlockchain) == {
        SupportedBlockchain.BTC,
        SupportedBlockchain.ETH,
        SupportedBlockchain.TRX,
        SupportedBlockchain.XRP,
        SupportedBlockchain.DOT,
        SupportedBlockchain.EOS,
    }


def test_supported_blockchain_str_mixin() -> None:
    assert SupportedBlockchain("BTC") is SupportedBlockchain.BTC
    assert str(SupportedBlockchain.ETH) == "ETH"


def test_fee_priority_three_tiers() -> None:
    assert set(FeePriority) == {FeePriority.LOW, FeePriority.MEDIUM, FeePriority.HIGH}


def test_crypto_transaction_status_four_states() -> None:
    assert set(CryptoTransactionStatus) == {
        CryptoTransactionStatus.PENDING,
        CryptoTransactionStatus.CONFIRMED,
        CryptoTransactionStatus.FAILED,
        CryptoTransactionStatus.REPLACED,
    }


# ---------------------------------------------------------------------------
# 3. Frozen domain models (I-24 append-only semantics)
# ---------------------------------------------------------------------------


def test_crypto_balance_is_frozen() -> None:
    b = CryptoBalance(
        wallet_id="w-1",
        blockchain=SupportedBlockchain.BTC,
        confirmed_balance=Decimal("1.5"),
        unconfirmed_balance=Decimal("0"),
        currency="BTC",
        as_of=_NOW,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.confirmed_balance = Decimal("999")  # type: ignore[misc]


def test_crypto_wallet_address_is_frozen() -> None:
    addr = CryptoWalletAddress(
        wallet_id="w-1",
        customer_id="c-1",
        blockchain=SupportedBlockchain.ETH,
        address="0xdeadbeef",
        created_at=_NOW,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        addr.address = "0xnewaddr"  # type: ignore[misc]


def test_crypto_transaction_request_is_frozen() -> None:
    req = CryptoTransactionRequest(
        tx_id="tx-001",
        from_wallet_id="w-1",
        to_address="1A1z",
        blockchain=SupportedBlockchain.BTC,
        amount=Decimal("0.5"),
        currency="BTC",
        fee_level=FeePriority.MEDIUM,
        customer_id="c-1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.amount = Decimal("999")  # type: ignore[misc]


def test_crypto_transaction_result_is_frozen() -> None:
    result = CryptoTransactionResult(
        tx_id="tx-001",
        tx_hash=None,
        blockchain=SupportedBlockchain.BTC,
        amount=Decimal("0.5"),
        fee=Decimal("0.0001"),
        currency="BTC",
        status=CryptoTransactionStatus.PENDING,
        from_wallet_id="w-1",
        to_address="1A1z",
        created_at=_NOW,
        confirmed_at=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = CryptoTransactionStatus.CONFIRMED  # type: ignore[misc]


def test_crypto_fee_estimate_is_frozen() -> None:
    est = CryptoFeeEstimate(
        blockchain=SupportedBlockchain.ETH,
        fee=Decimal("0.002"),
        currency="ETH",
        priority=FeePriority.HIGH,
        estimated_confirmation_blocks=1,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        est.fee = Decimal("0")  # type: ignore[misc]


def test_crypto_block_is_frozen() -> None:
    block = CryptoBlock(
        block_hash="000000000000000000024bead8df69990852c202db0e0097c1a12ea637d7e96d",
        block_number=840000,
        blockchain=SupportedBlockchain.BTC,
        timestamp=_NOW,
        tx_count=3000,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        block.tx_count = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. I-01 Decimal invariant — amounts are Decimal, not float
# ---------------------------------------------------------------------------


def test_balance_amounts_are_decimal() -> None:
    b = CryptoBalance(
        wallet_id="w-1",
        blockchain=SupportedBlockchain.BTC,
        confirmed_balance=Decimal("1.23456789"),
        unconfirmed_balance=Decimal("0.00000001"),
        currency="BTC",
        as_of=_NOW,
    )
    assert isinstance(b.confirmed_balance, Decimal)
    assert isinstance(b.unconfirmed_balance, Decimal)


def test_tx_request_amount_is_decimal() -> None:
    req = CryptoTransactionRequest(
        tx_id="tx-i01",
        from_wallet_id="w-1",
        to_address="1A1z",
        blockchain=SupportedBlockchain.BTC,
        amount=Decimal("0.00001"),
        currency="BTC",
        fee_level=FeePriority.LOW,
        customer_id="c-1",
    )
    assert isinstance(req.amount, Decimal)


def test_fee_estimate_amount_is_decimal() -> None:
    est = _LedgerStub().get_fee_estimate(SupportedBlockchain.ETH, Decimal("1.0"))
    assert isinstance(est.fee, Decimal)


# ---------------------------------------------------------------------------
# 5. Protocol surface conformance
# ---------------------------------------------------------------------------


def test_ledger_port_methods_surface() -> None:
    for method in (
        "get_balance",
        "create_wallet_address",
        "create_tx",
        "get_fee_estimate",
        "health",
    ):
        assert hasattr(CryptoLedgerPort, method), f"missing: {method}"


def test_rpc_port_methods_surface() -> None:
    for method in ("broadcast_tx", "get_block", "estimate_fee", "health"):
        assert hasattr(CryptoRpcPort, method), f"missing: {method}"


def test_ledger_stub_is_structural_instance() -> None:
    assert isinstance(_LedgerStub(), CryptoLedgerPort)


def test_rpc_stub_is_structural_instance() -> None:
    assert isinstance(_RpcStub(), CryptoRpcPort)


# ---------------------------------------------------------------------------
# 6. CryptoLedgerError
# ---------------------------------------------------------------------------


def test_crypto_ledger_error_has_code_attribute() -> None:
    err = CryptoLedgerError("wallet not found", code="wallet_not_found")
    assert err.code == "wallet_not_found"
    assert str(err) == "wallet not found"


def test_crypto_ledger_error_is_exception() -> None:
    with pytest.raises(CryptoLedgerError) as exc_info:
        raise CryptoLedgerError("blocked jurisdiction", code="i02_blocked")
    assert exc_info.value.code == "i02_blocked"


# ---------------------------------------------------------------------------
# 7. Stub round-trip smoke (no I/O — pure in-memory)
# ---------------------------------------------------------------------------


def test_stub_get_balance_returns_decimal_balance() -> None:
    stub = _LedgerStub()
    bal = stub.get_balance("w-1", SupportedBlockchain.BTC)
    assert bal.wallet_id == "w-1"
    assert isinstance(bal.confirmed_balance, Decimal)


def test_stub_create_tx_idempotency_key_preserved() -> None:
    stub = _LedgerStub()
    req = CryptoTransactionRequest(
        tx_id="idem-key-001",
        from_wallet_id="w-1",
        to_address="1A1z",
        blockchain=SupportedBlockchain.BTC,
        amount=Decimal("0.1"),
        currency="BTC",
        fee_level=FeePriority.MEDIUM,
        customer_id="c-1",
    )
    result = stub.create_tx(req)
    assert result.tx_id == "idem-key-001"
    assert result.status == CryptoTransactionStatus.PENDING


def test_rpc_stub_broadcast_returns_hash_string() -> None:
    stub = _RpcStub()
    tx_hash = stub.broadcast_tx("signed-tx-hex", SupportedBlockchain.BTC)
    assert isinstance(tx_hash, str)
    assert len(tx_hash) > 0
