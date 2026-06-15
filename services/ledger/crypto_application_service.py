"""
services/ledger/crypto_application_service.py
CryptoApplicationService — Wave E DI wiring (ADR-031, Phase 5 Step 1).

Routes method calls to the correct Wave-E legacy adapter:
  wallet     (REWRITE-7): get_balance, create_wallet_address
  processing (REWRITE-8): create_tx, get_fee_estimate
  rpc        (REWRITE-9): broadcast_tx, get_block, estimate_fee

No business logic — pure delegation. Real adapters replace in-memory
scaffolds when REWRITE-9 RPC dependency is available.
"""

from __future__ import annotations

from decimal import Decimal

from services.ledger.crypto_ledger_port import (
    CryptoBalance,
    CryptoBlock,
    CryptoFeeEstimate,
    CryptoLedgerPort,
    CryptoRpcPort,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoWalletAddress,
    FeePriority,
    SupportedBlockchain,
)


class CryptoApplicationService:
    """Composes REWRITE-7/8/9 legacy adapters — pure delegation, no business logic.

    Delegation map:
      _wallet     → get_balance, create_wallet_address
      _processing → create_tx, get_fee_estimate
      _rpc        → broadcast_tx, get_block, estimate_fee
    """

    def __init__(
        self,
        wallet: CryptoLedgerPort,
        processing: CryptoLedgerPort,
        rpc: CryptoRpcPort,
    ) -> None:
        self._wallet = wallet
        self._processing = processing
        self._rpc = rpc

    # ── REWRITE-7 (wallet) ───────────────────────────────────────────────────

    def get_balance(
        self,
        wallet_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBalance:
        return self._wallet.get_balance(wallet_id, blockchain)

    def create_wallet_address(
        self,
        customer_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoWalletAddress:
        return self._wallet.create_wallet_address(customer_id, blockchain)

    # ── REWRITE-8 (processing) ───────────────────────────────────────────────

    def create_tx(
        self,
        request: CryptoTransactionRequest,
    ) -> CryptoTransactionResult:
        return self._processing.create_tx(request)

    def get_fee_estimate(
        self,
        blockchain: SupportedBlockchain,
        amount: Decimal,
    ) -> CryptoFeeEstimate:
        return self._processing.get_fee_estimate(blockchain, amount)

    # ── REWRITE-9 (rpc) ──────────────────────────────────────────────────────

    def broadcast_tx(
        self,
        signed_tx: str,
        blockchain: SupportedBlockchain,
    ) -> str:
        return self._rpc.broadcast_tx(signed_tx, blockchain)

    def get_block(
        self,
        block_hash: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBlock:
        return self._rpc.get_block(block_hash, blockchain)

    def estimate_fee(
        self,
        blockchain: SupportedBlockchain,
        priority: FeePriority,
    ) -> CryptoFeeEstimate:
        return self._rpc.estimate_fee(blockchain, priority)

    # ── Aggregate health ─────────────────────────────────────────────────────

    def health(self) -> dict[str, bool]:
        return {
            "wallet": self._wallet.health(),
            "processing": self._processing.health(),
            "rpc": self._rpc.health(),
        }
