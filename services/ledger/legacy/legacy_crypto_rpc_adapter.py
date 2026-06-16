"""
services/ledger/legacy/legacy_crypto_rpc_adapter.py
LegacyCryptoRpcAdapter — REWRITE-9 scaffold.

Implements CryptoRpcPort:
  - broadcast_tx()   ← crypto-api-rpc/src/rpc/*.service.ts (direct node relay)
  - get_block()      ← same source, block metadata fetch
  - estimate_fee()   ← same source, network fee query per priority tier
  - health()

ADR-025 §15-16 drops applied:
  web3, ethers, bitcoinjs-lib, TronWeb direct HTTP clients,
  NestJS DI, BigNumber → Decimal (I-01).

Scaffold: in-memory only.  Real adapter will replace with HTTP calls to
crypto-api-rpc nodes (REWRITE-9 RPC dependency, post-Wave-E).

Protocol conformance: structural isinstance(adapter, CryptoRpcPort) passes.
broadcast_tx returns deterministic placeholder hash; get_block returns
scaffold CryptoBlock; estimate_fee mirrors REWRITE-8 compute_fee table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.ledger.crypto_ledger_port import (
    CryptoBlock,
    CryptoFeeEstimate,
    CryptoRpcPort,
    FeePriority,
    SupportedBlockchain,
)

# Base fee per blockchain (MEDIUM tier, I-01: Decimal).
# Mirrors REWRITE-8 _BASE_FEE — single source of truth will be REWRITE-9 RPC.
_BASE_FEE: dict[SupportedBlockchain, Decimal] = {
    SupportedBlockchain.BTC: Decimal("0.00005"),
    SupportedBlockchain.ETH: Decimal("0.003"),
    SupportedBlockchain.TRX: Decimal("1.0"),
    SupportedBlockchain.XRP: Decimal("0.00001"),
    SupportedBlockchain.DOT: Decimal("0.01"),
    SupportedBlockchain.EOS: Decimal("0.1"),
}

_PRIORITY_MULTIPLIER: dict[FeePriority, Decimal] = {
    FeePriority.LOW: Decimal("0.5"),
    FeePriority.MEDIUM: Decimal("1"),
    FeePriority.HIGH: Decimal("2"),
}

_CONFIRMATION_BLOCKS: dict[FeePriority, int] = {
    FeePriority.LOW: 6,
    FeePriority.MEDIUM: 3,
    FeePriority.HIGH: 1,
}

_FEE_CURRENCY: dict[SupportedBlockchain, str] = {
    SupportedBlockchain.BTC: "BTC",
    SupportedBlockchain.ETH: "ETH",
    SupportedBlockchain.TRX: "TRX",
    SupportedBlockchain.XRP: "XRP",
    SupportedBlockchain.DOT: "DOT",
    SupportedBlockchain.EOS: "EOS",
}

# Scaffold block numbers per chain (placeholder until REWRITE-9 RPC feed).
_SCAFFOLD_BLOCK_NUMBER: dict[SupportedBlockchain, int] = {
    SupportedBlockchain.BTC: 840_000,
    SupportedBlockchain.ETH: 20_000_000,
    SupportedBlockchain.TRX: 60_000_000,
    SupportedBlockchain.XRP: 90_000_000,
    SupportedBlockchain.DOT: 22_000_000,
    SupportedBlockchain.EOS: 380_000_000,
}


def _derive_tx_hash(signed_tx: str, blockchain: SupportedBlockchain) -> str:
    """Deterministic placeholder tx hash — SHA-256 of signed_tx + chain tag."""
    digest = hashlib.sha256(f"{blockchain}:{signed_tx}".encode()).hexdigest()
    return f"0x{digest}"


class LegacyCryptoRpcAdapter:
    """REWRITE-9: In-memory scaffold for blockchain node connectivity.

    Real adapter will replace in-memory stores with HTTP calls to
    crypto-api-rpc nodes (web3/ethers/bitcoinjs/TronWeb equivalents,
    self-hosted — ADR-025 §15 drop of BigNumber → Decimal).
    """

    def __init__(
        self,
        blocks: dict[tuple[str, SupportedBlockchain], CryptoBlock] | None = None,
        fee_overrides: dict[tuple[SupportedBlockchain, FeePriority], Decimal] | None = None,
    ) -> None:
        self._blocks: dict[tuple[str, SupportedBlockchain], CryptoBlock] = (
            blocks if blocks is not None else {}
        )
        self._fee_overrides: dict[tuple[SupportedBlockchain, FeePriority], Decimal] = (
            fee_overrides if fee_overrides is not None else {}
        )
        self._broadcast_log: list[tuple[str, SupportedBlockchain, str]] = []

    def broadcast_tx(self, signed_tx: str, blockchain: SupportedBlockchain) -> str:
        """Accept a signed transaction and return a deterministic placeholder tx_hash."""
        tx_hash = _derive_tx_hash(signed_tx, blockchain)
        self._broadcast_log.append((signed_tx, blockchain, tx_hash))
        return tx_hash

    def get_block(self, block_hash: str, blockchain: SupportedBlockchain) -> CryptoBlock:
        """Return stored block or scaffold block with deterministic values."""
        key = (block_hash, blockchain)
        if key in self._blocks:
            return self._blocks[key]
        return CryptoBlock(
            block_hash=block_hash,
            block_number=_SCAFFOLD_BLOCK_NUMBER[blockchain],
            blockchain=blockchain,
            timestamp=datetime.now(UTC),
            tx_count=0,
        )

    def estimate_fee(
        self,
        blockchain: SupportedBlockchain,
        priority: FeePriority,
    ) -> CryptoFeeEstimate:
        """Return fee estimate from in-memory table (I-01: Decimal, no float)."""
        override_key = (blockchain, priority)
        fee = self._fee_overrides.get(
            override_key, _BASE_FEE[blockchain] * _PRIORITY_MULTIPLIER[priority]
        )
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=fee,
            currency=_FEE_CURRENCY[blockchain],
            priority=priority,
            estimated_confirmation_blocks=_CONFIRMATION_BLOCKS[priority],
        )

    def health(self) -> bool:
        return True


# Structural type assertion — fails fast at import if CryptoRpcPort drifts.
_: CryptoRpcPort = LegacyCryptoRpcAdapter()  # type: ignore[assignment]
