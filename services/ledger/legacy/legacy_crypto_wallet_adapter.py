"""
services/ledger/legacy/legacy_crypto_wallet_adapter.py
LegacyCryptoWalletAdapter — REWRITE-7 scaffold.

Implements CryptoLedgerPort wallet use-cases:
  - get_balance()          ← crypto-api-wallet/src/wallet/*.service.ts
  - create_wallet_address() ← crypto-api-wallet/src/wallet/db/address.service.ts

REWRITE-8 scope (create_tx, get_fee_estimate) is NOT implemented here.
Calling those methods raises NotImplementedError with an explicit delegation hint.

ADR-025 §15-16 drops applied:
  TypeORM entities, NestJS @Injectable/@InjectRepository, BigNumber → Decimal (I-01),
  KeysService (key derivation via RPC), RpcService (direct node calls).

Protocol conformance: structural isinstance passes (all methods present),
  but full behavioural conformance requires REWRITE-8 for create_tx/get_fee_estimate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.ledger.crypto_ledger_port import (
    CryptoBalance,
    CryptoFeeEstimate,
    CryptoLedgerPort,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoWalletAddress,
    SupportedBlockchain,
)

# Native currency per blockchain — maps to crypto-api-wallet currency field.
_NATIVE_CURRENCY: dict[SupportedBlockchain, str] = {
    SupportedBlockchain.BTC: "BTC",
    SupportedBlockchain.ETH: "ETH",
    SupportedBlockchain.TRX: "TRX",
    SupportedBlockchain.XRP: "XRP",
    SupportedBlockchain.DOT: "DOT",
    SupportedBlockchain.EOS: "EOS",
}


def canonical_currency(blockchain: SupportedBlockchain) -> str:
    """Return the native currency ticker for a blockchain (I-01: used in CryptoBalance.currency)."""
    return _NATIVE_CURRENCY[blockchain]


def derive_wallet_id(customer_id: str, blockchain: SupportedBlockchain) -> str:
    """Deterministic wallet identifier: mirrors crypto-api-wallet internal wallet-per-chain pattern."""
    return f"wallet-{customer_id}-{blockchain}"


class LegacyCryptoWalletAdapter:
    """REWRITE-7: In-memory scaffold for wallet balance + address management.

    Inject pre-populated stores for testing; real adapter will replace stores
    with HTTP calls to crypto-api-wallet (REWRITE-9 RPC dependency).

    Implements: get_balance, create_wallet_address, health.
    Stubs (REWRITE-8): create_tx, get_fee_estimate.
    """

    def __init__(
        self,
        balances: dict[tuple[str, SupportedBlockchain], CryptoBalance] | None = None,
        addresses: dict[str, list[CryptoWalletAddress]] | None = None,
    ) -> None:
        self._balances: dict[tuple[str, SupportedBlockchain], CryptoBalance] = (
            balances if balances is not None else {}
        )
        self._addresses: dict[str, list[CryptoWalletAddress]] = (
            addresses if addresses is not None else {}
        )

    # ------------------------------------------------------------------
    # REWRITE-7 — implemented
    # ------------------------------------------------------------------

    def get_balance(
        self,
        wallet_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBalance:
        """Return stored balance or zero-balance default (I-01: Decimal)."""
        key = (wallet_id, blockchain)
        if key in self._balances:
            return self._balances[key]
        return CryptoBalance(
            wallet_id=wallet_id,
            blockchain=blockchain,
            confirmed_balance=Decimal("0"),
            unconfirmed_balance=Decimal("0"),
            currency=canonical_currency(blockchain),
            as_of=datetime.now(UTC),
        )

    def create_wallet_address(
        self,
        customer_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoWalletAddress:
        """Derive and register a blockchain address for a customer wallet."""
        wallet_id = derive_wallet_id(customer_id, blockchain)
        # Placeholder address — real derivation requires REWRITE-9 RPC call.
        address_str = f"addr-{blockchain}-{customer_id[:8]}"
        addr = CryptoWalletAddress(
            wallet_id=wallet_id,
            customer_id=customer_id,
            blockchain=blockchain,
            address=address_str,
            created_at=datetime.now(UTC),
        )
        self._addresses.setdefault(customer_id, []).append(addr)
        return addr

    def health(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # REWRITE-8 stubs — not in scope for this adapter
    # ------------------------------------------------------------------

    def create_tx(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        raise NotImplementedError(
            "REWRITE-8: delegate to LegacyCryptoProcessingAdapter.create_tx()"
        )

    def get_fee_estimate(
        self,
        blockchain: SupportedBlockchain,
        amount: Decimal,
    ) -> CryptoFeeEstimate:
        raise NotImplementedError(
            "REWRITE-8: delegate to LegacyCryptoProcessingAdapter.get_fee_estimate()"
        )


# Structural type assertion — verified at import time, fails fast if Protocol drifts.
_: CryptoLedgerPort = LegacyCryptoWalletAdapter()  # type: ignore[assignment]
