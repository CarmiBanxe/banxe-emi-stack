"""
tests/test_legacy_crypto_wallet_adapter.py — REWRITE-7 scaffold tests.

Covers: module import safety, adapter surface existence, structural Protocol
conformance (method presence only — REWRITE-8 stubs raise NotImplementedError),
mapping/normalization determinism, zero-balance default, address creation,
no runtime side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.ledger.crypto_ledger_port import (
    CryptoBalance,
    CryptoLedgerPort,
    CryptoTransactionRequest,
    CryptoWalletAddress,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.legacy.legacy_crypto_wallet_adapter import (
    LegacyCryptoWalletAdapter,
    canonical_currency,
    derive_wallet_id,
)

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)

_ALL_CHAINS = list(SupportedBlockchain)


# ---------------------------------------------------------------------------
# 1. Module import safety
# ---------------------------------------------------------------------------


def test_module_imports_cleanly() -> None:
    import importlib

    mod = importlib.import_module("services.ledger.legacy.legacy_crypto_wallet_adapter")
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Adapter surface
# ---------------------------------------------------------------------------


def test_adapter_has_get_balance() -> None:
    assert hasattr(LegacyCryptoWalletAdapter, "get_balance")


def test_adapter_has_create_wallet_address() -> None:
    assert hasattr(LegacyCryptoWalletAdapter, "create_wallet_address")


def test_adapter_has_health() -> None:
    assert hasattr(LegacyCryptoWalletAdapter, "health")


def test_adapter_has_create_tx_stub() -> None:
    assert hasattr(LegacyCryptoWalletAdapter, "create_tx")


def test_adapter_has_get_fee_estimate_stub() -> None:
    assert hasattr(LegacyCryptoWalletAdapter, "get_fee_estimate")


# ---------------------------------------------------------------------------
# 3. Structural Protocol conformance (method-presence check only)
#    Full behavioural conformance requires REWRITE-8 for create_tx / get_fee_estimate.
# ---------------------------------------------------------------------------


def test_adapter_is_structural_instance_of_crypto_ledger_port() -> None:
    adapter = LegacyCryptoWalletAdapter()
    assert isinstance(adapter, CryptoLedgerPort)


# ---------------------------------------------------------------------------
# 4. canonical_currency — deterministic mapping for all 6 chains
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
def test_canonical_currency_all_chains(blockchain: SupportedBlockchain, expected: str) -> None:
    assert canonical_currency(blockchain) == expected


# ---------------------------------------------------------------------------
# 5. derive_wallet_id — deterministic, encodes customer + chain
# ---------------------------------------------------------------------------


def test_derive_wallet_id_is_deterministic() -> None:
    wid1 = derive_wallet_id("cust-001", SupportedBlockchain.BTC)
    wid2 = derive_wallet_id("cust-001", SupportedBlockchain.BTC)
    assert wid1 == wid2


def test_derive_wallet_id_differs_by_blockchain() -> None:
    btc = derive_wallet_id("cust-001", SupportedBlockchain.BTC)
    eth = derive_wallet_id("cust-001", SupportedBlockchain.ETH)
    assert btc != eth


def test_derive_wallet_id_contains_customer_id() -> None:
    wid = derive_wallet_id("cust-xyz", SupportedBlockchain.XRP)
    assert "cust-xyz" in wid


# ---------------------------------------------------------------------------
# 6. get_balance — zero default + stored balance
# ---------------------------------------------------------------------------


def test_get_balance_returns_crypto_balance() -> None:
    adapter = LegacyCryptoWalletAdapter()
    bal = adapter.get_balance("w-001", SupportedBlockchain.BTC)
    assert isinstance(bal, CryptoBalance)


def test_get_balance_zero_default_decimal() -> None:
    adapter = LegacyCryptoWalletAdapter()
    bal = adapter.get_balance("w-unknown", SupportedBlockchain.ETH)
    assert bal.confirmed_balance == Decimal("0")
    assert bal.unconfirmed_balance == Decimal("0")
    assert isinstance(bal.confirmed_balance, Decimal)


def test_get_balance_zero_default_currency_matches_blockchain() -> None:
    adapter = LegacyCryptoWalletAdapter()
    bal = adapter.get_balance("w-001", SupportedBlockchain.TRX)
    assert bal.currency == "TRX"


def test_get_balance_returns_stored_value() -> None:
    stored = CryptoBalance(
        wallet_id="w-btc",
        blockchain=SupportedBlockchain.BTC,
        confirmed_balance=Decimal("1.5"),
        unconfirmed_balance=Decimal("0.25"),
        currency="BTC",
        as_of=_NOW,
    )
    adapter = LegacyCryptoWalletAdapter(balances={("w-btc", SupportedBlockchain.BTC): stored})
    result = adapter.get_balance("w-btc", SupportedBlockchain.BTC)
    assert result.confirmed_balance == Decimal("1.5")
    assert result.unconfirmed_balance == Decimal("0.25")


def test_get_balance_stored_wallet_id_preserved() -> None:
    stored = CryptoBalance(
        wallet_id="w-eth",
        blockchain=SupportedBlockchain.ETH,
        confirmed_balance=Decimal("2.0"),
        unconfirmed_balance=Decimal("0"),
        currency="ETH",
        as_of=_NOW,
    )
    adapter = LegacyCryptoWalletAdapter(balances={("w-eth", SupportedBlockchain.ETH): stored})
    result = adapter.get_balance("w-eth", SupportedBlockchain.ETH)
    assert result.wallet_id == "w-eth"


# ---------------------------------------------------------------------------
# 7. create_wallet_address
# ---------------------------------------------------------------------------


def test_create_wallet_address_returns_crypto_wallet_address() -> None:
    adapter = LegacyCryptoWalletAdapter()
    addr = adapter.create_wallet_address("cust-001", SupportedBlockchain.BTC)
    assert isinstance(addr, CryptoWalletAddress)


def test_create_wallet_address_customer_id_bound() -> None:
    adapter = LegacyCryptoWalletAdapter()
    addr = adapter.create_wallet_address("cust-42", SupportedBlockchain.ETH)
    assert addr.customer_id == "cust-42"


def test_create_wallet_address_blockchain_bound() -> None:
    adapter = LegacyCryptoWalletAdapter()
    addr = adapter.create_wallet_address("cust-001", SupportedBlockchain.XRP)
    assert addr.blockchain == SupportedBlockchain.XRP


def test_create_wallet_address_address_is_string() -> None:
    adapter = LegacyCryptoWalletAdapter()
    addr = adapter.create_wallet_address("cust-001", SupportedBlockchain.DOT)
    assert isinstance(addr.address, str)
    assert len(addr.address) > 0


def test_create_wallet_address_multiple_calls_accumulate() -> None:
    adapter = LegacyCryptoWalletAdapter()
    adapter.create_wallet_address("cust-001", SupportedBlockchain.BTC)
    adapter.create_wallet_address("cust-001", SupportedBlockchain.ETH)
    assert len(adapter._addresses["cust-001"]) == 2


def test_create_wallet_address_created_at_is_datetime() -> None:
    adapter = LegacyCryptoWalletAdapter()
    addr = adapter.create_wallet_address("cust-001", SupportedBlockchain.EOS)
    assert isinstance(addr.created_at, datetime)
    assert addr.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 8. REWRITE-8 stubs — explicit delegation markers
# ---------------------------------------------------------------------------


def test_create_tx_raises_not_implemented() -> None:
    adapter = LegacyCryptoWalletAdapter()
    req = CryptoTransactionRequest(
        tx_id="tx-001",
        from_wallet_id="w-1",
        to_address="1A1z",
        blockchain=SupportedBlockchain.BTC,
        amount=Decimal("0.1"),
        currency="BTC",
        fee_level=FeePriority.MEDIUM,
        customer_id="cust-001",
    )
    with pytest.raises(NotImplementedError):
        adapter.create_tx(req)


def test_get_fee_estimate_raises_not_implemented() -> None:
    adapter = LegacyCryptoWalletAdapter()
    with pytest.raises(NotImplementedError):
        adapter.get_fee_estimate(SupportedBlockchain.ETH, Decimal("1.0"))


# ---------------------------------------------------------------------------
# 9. health
# ---------------------------------------------------------------------------


def test_health_returns_true() -> None:
    adapter = LegacyCryptoWalletAdapter()
    assert adapter.health() is True
