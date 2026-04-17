"""
services/crypto_custody/models.py — Domain models for Crypto & Digital Assets Custody
IL-CDC-01 | Phase 35 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable


class AssetType(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    USDT = "USDT"
    USDC = "USDC"
    SOL = "SOL"
    XRP = "XRP"
    DOGE = "DOGE"


class WalletStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    FROZEN = "FROZEN"
    PENDING_CREATION = "PENDING_CREATION"


class TransferStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    HITL_REQUIRED = "HITL_REQUIRED"
    EXECUTING = "EXECUTING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class CustodyAction(str, Enum):
    CREATE_WALLET = "CREATE_WALLET"
    ARCHIVE_WALLET = "ARCHIVE_WALLET"
    INITIATE_TRANSFER = "INITIATE_TRANSFER"
    CONFIRM_TRANSFER = "CONFIRM_TRANSFER"
    RECONCILE = "RECONCILE"


class NetworkType(str, Enum):
    MAINNET = "MAINNET"
    TESTNET = "TESTNET"
    DEVNET = "DEVNET"


@dataclasses.dataclass(frozen=True)
class WalletRecord:
    id: str
    asset_type: AssetType
    status: WalletStatus
    address: str
    balance: Decimal
    network: NetworkType
    created_at: datetime
    updated_at: datetime
    owner_id: str


@dataclasses.dataclass(frozen=True)
class TransferRecord:
    id: str
    from_wallet_id: str
    to_address: str
    asset_type: AssetType
    amount: Decimal
    network_fee: Decimal
    status: TransferStatus
    travel_rule_required: bool
    created_at: datetime
    txhash: str | None = None


@dataclasses.dataclass(frozen=True)
class TravelRuleData:
    originator_name: str
    originator_iban: str
    originator_address: str
    beneficiary_name: str
    beneficiary_vasp: str
    amount: Decimal
    asset_type: AssetType
    jurisdiction: str


@dataclasses.dataclass(frozen=True)
class ReconciliationResult:
    wallet_id: str
    on_chain_balance: Decimal
    off_chain_balance: Decimal
    discrepancy: Decimal
    status: str  # "MATCHED" | "DISCREPANCY"
    timestamp: datetime


@dataclasses.dataclass(frozen=True)
class FeeEstimate:
    asset_type: AssetType
    network_fee: Decimal
    withdrawal_fee: Decimal
    total_fee: Decimal
    currency: str


@runtime_checkable
class WalletPort(Protocol):
    def get_wallet(self, wallet_id: str) -> WalletRecord | None: ...
    def list_wallets(self, owner_id: str) -> list[WalletRecord]: ...
    def save_wallet(self, wallet: WalletRecord) -> None: ...


@runtime_checkable
class TransferPort(Protocol):
    def get_transfer(self, transfer_id: str) -> TransferRecord | None: ...
    def save_transfer(self, transfer: TransferRecord) -> None: ...
    def list_transfers(self, wallet_id: str) -> list[TransferRecord]: ...


@runtime_checkable
class AuditPort(Protocol):
    def log(self, action: str, resource_id: str, details: str, outcome: str) -> None: ...


@runtime_checkable
class OnChainPort(Protocol):
    def get_balance(self, address: str, asset_type: AssetType, network: NetworkType) -> Decimal: ...
    def validate_address(self, address: str, asset_type: AssetType) -> bool: ...


class InMemoryWalletStore:
    """In-memory wallet store seeded with 3 sample wallets."""

    def __init__(self) -> None:
        now = datetime(2026, 1, 1, 0, 0, 0)
        self._data: dict[str, WalletRecord] = {
            "wallet-btc-001": WalletRecord(
                id="wallet-btc-001",
                asset_type=AssetType.BTC,
                status=WalletStatus.ACTIVE,
                address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf6n",
                balance=Decimal("0.50000000"),
                network=NetworkType.MAINNET,
                created_at=now,
                updated_at=now,
                owner_id="owner-001",
            ),
            "wallet-eth-001": WalletRecord(
                id="wallet-eth-001",
                asset_type=AssetType.ETH,
                status=WalletStatus.ACTIVE,
                address="0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
                balance=Decimal("2.50000000"),
                network=NetworkType.MAINNET,
                created_at=now,
                updated_at=now,
                owner_id="owner-001",
            ),
            "wallet-usdt-001": WalletRecord(
                id="wallet-usdt-001",
                asset_type=AssetType.USDT,
                status=WalletStatus.ACTIVE,
                address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
                balance=Decimal("5000.00000000"),
                network=NetworkType.MAINNET,
                created_at=now,
                updated_at=now,
                owner_id="owner-001",
            ),
        }

    def get_wallet(self, wallet_id: str) -> WalletRecord | None:
        return self._data.get(wallet_id)

    def list_wallets(self, owner_id: str) -> list[WalletRecord]:
        return [w for w in self._data.values() if w.owner_id == owner_id]

    def save_wallet(self, wallet: WalletRecord) -> None:
        self._data[wallet.id] = wallet


class InMemoryTransferStore:
    def __init__(self) -> None:
        self._data: dict[str, TransferRecord] = {}
        self._by_wallet: dict[str, list[str]] = {}

    def get_transfer(self, transfer_id: str) -> TransferRecord | None:
        return self._data.get(transfer_id)

    def save_transfer(self, transfer: TransferRecord) -> None:
        self._data[transfer.id] = transfer
        lst = self._by_wallet.setdefault(transfer.from_wallet_id, [])
        if transfer.id not in lst:
            lst.append(transfer.id)

    def list_transfers(self, wallet_id: str) -> list[TransferRecord]:
        ids = self._by_wallet.get(wallet_id, [])
        return [self._data[i] for i in ids if i in self._data]


class InMemoryAuditStore:
    """Append-only audit store (I-24)."""

    def __init__(self) -> None:
        self._records: list[dict[str, str]] = []

    def log(self, action: str, resource_id: str, details: str, outcome: str) -> None:
        self._records.append(
            {"action": action, "resource_id": resource_id, "details": details, "outcome": outcome}
        )

    def get_records(self) -> list[dict[str, str]]:
        return list(self._records)


class InMemoryOnChainStore:
    """Stub on-chain adapter — returns deterministic balances."""

    def get_balance(self, address: str, asset_type: AssetType, network: NetworkType) -> Decimal:
        return Decimal("1.00000000")

    def validate_address(self, address: str, asset_type: AssetType) -> bool:
        if asset_type == AssetType.BTC:
            return len(address) >= 25 and address[0] in ("1", "3", "b")
        return len(address) >= 20
