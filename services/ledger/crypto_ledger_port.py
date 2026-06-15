"""
services/ledger/crypto_ledger_port.py
CryptoLedgerPort + CryptoRpcPort — hexagonal Protocols for crypto wallet / ledger ops.

ADR-031 (Proposed) · Wave E prerequisite
Adapters land in services/ledger/legacy/ (REWRITE-7 wallet, REWRITE-8 processing, REWRITE-9 rpc).

I-01: All monetary amounts are Decimal — never float.
I-02: Blocked-jurisdiction enforcement is adapter responsibility, not port contract.
I-24: CryptoTransactionResult is immutable (frozen dataclass) — append-only semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable


class SupportedBlockchain(StrEnum):
    """Blockchains supported by the Banxe crypto platform (crypto-api-rpc source set)."""

    BTC = "BTC"
    ETH = "ETH"
    TRX = "TRX"
    XRP = "XRP"
    DOT = "DOT"
    EOS = "EOS"


class FeePriority(StrEnum):
    """Transaction fee priority tiers — maps to blockchain-native fee levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CryptoTransactionStatus(StrEnum):
    """Canonical lifecycle states for a crypto transaction (matches crypto-api-wallet source)."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    REPLACED = "REPLACED"  # EVM nonce-replacement or RBF


@dataclass(frozen=True)
class CryptoBalance:
    """Current balance snapshot for one wallet × blockchain pair (I-01: Decimal)."""

    wallet_id: str
    blockchain: SupportedBlockchain
    confirmed_balance: Decimal
    unconfirmed_balance: Decimal
    currency: str  # canonical ticker: "BTC", "ETH", "USDT", …
    as_of: datetime


@dataclass(frozen=True)
class CryptoWalletAddress:
    """Derived or imported blockchain address bound to a customer wallet."""

    wallet_id: str
    customer_id: str
    blockchain: SupportedBlockchain
    address: str
    created_at: datetime


@dataclass(frozen=True)
class CryptoTransactionRequest:
    """Instruction to post a crypto transfer (I-01: amount is Decimal, tx_id idempotency key)."""

    tx_id: str  # client-supplied idempotency key
    from_wallet_id: str
    to_address: str
    blockchain: SupportedBlockchain
    amount: Decimal  # I-01 — NEVER float
    currency: str
    fee_level: FeePriority
    customer_id: str


@dataclass(frozen=True)
class CryptoTransactionResult:
    """Outcome of create_tx — immutable after posting (I-24: append-only semantics)."""

    tx_id: str
    tx_hash: str | None  # None until broadcast accepted by node
    blockchain: SupportedBlockchain
    amount: Decimal  # I-01
    fee: Decimal  # I-01
    currency: str
    status: CryptoTransactionStatus
    from_wallet_id: str
    to_address: str
    created_at: datetime
    confirmed_at: datetime | None


@dataclass(frozen=True)
class CryptoFeeEstimate:
    """Fee estimate for a blockchain transaction (I-01: fee is Decimal)."""

    blockchain: SupportedBlockchain
    fee: Decimal  # I-01
    currency: str  # fee currency (may differ from tx currency, e.g. ETH for ERC-20)
    priority: FeePriority
    estimated_confirmation_blocks: int


@dataclass(frozen=True)
class CryptoBlock:
    """Block metadata returned by CryptoRpcPort.get_block()."""

    block_hash: str
    block_number: int
    blockchain: SupportedBlockchain
    timestamp: datetime
    tx_count: int


class CryptoLedgerError(Exception):
    """Raised by CryptoLedgerPort adapters on domain violations."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@runtime_checkable
class CryptoLedgerPort(Protocol):
    """Port for crypto wallet operations and transaction ledger.

    Adapters (Wave E):
      REWRITE-7 → legacy_crypto_wallet_adapter.py  (wallet/balance/address)
      REWRITE-8 → legacy_crypto_processing_adapter.py  (create_tx / fees)
    """

    def get_balance(
        self,
        wallet_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBalance:
        """Return current confirmed + unconfirmed balance for a wallet."""
        ...

    def create_wallet_address(
        self,
        customer_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoWalletAddress:
        """Derive or register a new blockchain address for a customer."""
        ...

    def create_tx(
        self,
        request: CryptoTransactionRequest,
    ) -> CryptoTransactionResult:
        """Post a crypto transfer; idempotent on tx_id within confirmation window."""
        ...

    def get_fee_estimate(
        self,
        blockchain: SupportedBlockchain,
        amount: Decimal,
    ) -> CryptoFeeEstimate:
        """Estimate network fee for a transfer of given amount on given blockchain."""
        ...

    def health(self) -> bool:
        """Return True if the adapter's backing store is reachable."""
        ...


@runtime_checkable
class CryptoRpcPort(Protocol):
    """Port for direct blockchain node connectivity (REWRITE-9).

    Adapter: legacy_crypto_rpc_adapter.py
    Drops: web3, ethers, bitcoinjs-lib, TronWeb direct HTTP clients.
    """

    def broadcast_tx(
        self,
        signed_tx: str,
        blockchain: SupportedBlockchain,
    ) -> str:
        """Broadcast a signed transaction; returns tx_hash."""
        ...

    def get_block(
        self,
        block_hash: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBlock:
        """Fetch block metadata by hash."""
        ...

    def estimate_fee(
        self,
        blockchain: SupportedBlockchain,
        priority: FeePriority,
    ) -> CryptoFeeEstimate:
        """Query current network fee for given priority tier."""
        ...

    def health(self) -> bool:
        """Return True if the RPC node is reachable."""
        ...
