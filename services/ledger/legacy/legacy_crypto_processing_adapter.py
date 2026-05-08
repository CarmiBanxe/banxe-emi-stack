"""
services/ledger/legacy/legacy_crypto_processing_adapter.py
LegacyCryptoProcessingAdapter — REWRITE-8 scaffold.

Implements CryptoLedgerPort processing use-cases:
  - create_tx()          ← crypto-processing-backend/src/queues-consumers/
                           transaction-queues-fee-consumer.service.ts
  - get_fee_estimate()   ← same source, fee transfer flow
  - health()

REWRITE-7 scope (get_balance, create_wallet_address) raises NotImplementedError
and must be delegated to LegacyCryptoWalletAdapter.

ADR-025 §15-16 drops applied:
  Bull @Processor/@Process, TypeORM Connection/EntityManager,
  RabbitMQ producers, NestJS DI, BigNumber → Decimal (I-01).

Protocol conformance: structural isinstance passes (all methods present).
Idempotency: create_tx is idempotent on tx_id — matches legacy invoice/fee
consumer behavior (deduplicate on client-supplied key within confirmation window).
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
    CryptoTransactionStatus,
    CryptoWalletAddress,
    FeePriority,
    SupportedBlockchain,
)

# Base fee per blockchain (MEDIUM tier, I-01: Decimal).
# Derived from crypto-processing-backend fee schedules; placeholders until REWRITE-9 RPC feed.
_BASE_FEE: dict[SupportedBlockchain, Decimal] = {
    SupportedBlockchain.BTC: Decimal("0.00005"),
    SupportedBlockchain.ETH: Decimal("0.003"),
    SupportedBlockchain.TRX: Decimal("1.0"),
    SupportedBlockchain.XRP: Decimal("0.00001"),
    SupportedBlockchain.DOT: Decimal("0.01"),
    SupportedBlockchain.EOS: Decimal("0.1"),
}

# Priority multipliers — deterministic tier scaling, no I/O.
_PRIORITY_MULTIPLIER: dict[FeePriority, Decimal] = {
    FeePriority.LOW: Decimal("0.5"),
    FeePriority.MEDIUM: Decimal("1"),
    FeePriority.HIGH: Decimal("2"),
}

# Estimated confirmation blocks per priority (scaffold values).
_CONFIRMATION_BLOCKS: dict[FeePriority, int] = {
    FeePriority.LOW: 6,
    FeePriority.MEDIUM: 3,
    FeePriority.HIGH: 1,
}

# Native fee currency per blockchain (matches canonical_currency in REWRITE-7).
_FEE_CURRENCY: dict[SupportedBlockchain, str] = {
    SupportedBlockchain.BTC: "BTC",
    SupportedBlockchain.ETH: "ETH",
    SupportedBlockchain.TRX: "TRX",
    SupportedBlockchain.XRP: "XRP",
    SupportedBlockchain.DOT: "DOT",
    SupportedBlockchain.EOS: "EOS",
}


def compute_fee(blockchain: SupportedBlockchain, priority: FeePriority) -> Decimal:
    """Deterministic fee calculation (I-01: Decimal, no float)."""
    return _BASE_FEE[blockchain] * _PRIORITY_MULTIPLIER[priority]


def fee_currency(blockchain: SupportedBlockchain) -> str:
    """Return the fee denomination currency for a blockchain."""
    return _FEE_CURRENCY[blockchain]


class LegacyCryptoProcessingAdapter:
    """REWRITE-8: In-memory scaffold for transaction creation and fee estimation.

    Inject pre-populated stores for testing; real adapter will replace the
    in-memory tx store with a DB write and the fee lookup with REWRITE-9 RPC.
    """

    def __init__(
        self,
        transactions: dict[str, CryptoTransactionResult] | None = None,
        fee_overrides: dict[tuple[SupportedBlockchain, FeePriority], Decimal] | None = None,
    ) -> None:
        self._transactions: dict[str, CryptoTransactionResult] = (
            transactions if transactions is not None else {}
        )
        self._fee_overrides: dict[tuple[SupportedBlockchain, FeePriority], Decimal] = (
            fee_overrides if fee_overrides is not None else {}
        )

    # ------------------------------------------------------------------
    # REWRITE-8 — implemented
    # ------------------------------------------------------------------

    def create_tx(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        """Idempotent on tx_id — second call with same key returns the stored result (I-01)."""
        if request.tx_id in self._transactions:
            return self._transactions[request.tx_id]
        override_key = (request.blockchain, request.fee_level)
        fee = self._fee_overrides.get(
            override_key, compute_fee(request.blockchain, request.fee_level)
        )
        result = CryptoTransactionResult(
            tx_id=request.tx_id,
            tx_hash=None,  # assigned after REWRITE-9 broadcast
            blockchain=request.blockchain,
            amount=request.amount,
            fee=fee,
            currency=request.currency,
            status=CryptoTransactionStatus.PENDING,
            from_wallet_id=request.from_wallet_id,
            to_address=request.to_address,
            created_at=datetime.now(UTC),
            confirmed_at=None,
        )
        self._transactions[request.tx_id] = result
        return result

    def get_fee_estimate(
        self,
        blockchain: SupportedBlockchain,
        amount: Decimal,  # available for future adapters; scaffold uses fixed table
    ) -> CryptoFeeEstimate:
        """Return fee estimate for MEDIUM priority (default tier, no RPC call)."""
        priority = FeePriority.MEDIUM
        override_key = (blockchain, priority)
        fee = self._fee_overrides.get(override_key, compute_fee(blockchain, priority))
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=fee,
            currency=fee_currency(blockchain),
            priority=priority,
            estimated_confirmation_blocks=_CONFIRMATION_BLOCKS[priority],
        )

    def health(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # REWRITE-7 stubs — not in scope for this adapter
    # ------------------------------------------------------------------

    def get_balance(
        self,
        wallet_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBalance:
        raise NotImplementedError("REWRITE-7: delegate to LegacyCryptoWalletAdapter.get_balance()")

    def create_wallet_address(
        self,
        customer_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoWalletAddress:
        raise NotImplementedError(
            "REWRITE-7: delegate to LegacyCryptoWalletAdapter.create_wallet_address()"
        )


# Structural type assertion — fails fast at import if Protocol drifts.
_: CryptoLedgerPort = LegacyCryptoProcessingAdapter()  # type: ignore[assignment]
