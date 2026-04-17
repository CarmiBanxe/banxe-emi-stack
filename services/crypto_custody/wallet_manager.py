"""
services/crypto_custody/wallet_manager.py — Wallet creation and management
IL-CDC-01 | Phase 35 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import uuid

from services.crypto_custody.crypto_agent import CryptoAgent, HITLProposal
from services.crypto_custody.models import (
    AssetType,
    AuditPort,
    InMemoryAuditStore,
    InMemoryWalletStore,
    NetworkType,
    WalletPort,
    WalletRecord,
    WalletStatus,
)

_ETH_LIKE = {AssetType.ETH, AssetType.USDT, AssetType.USDC}
_BTC_LIKE = {AssetType.BTC}


def _generate_address(owner_id: str, asset_type: AssetType) -> str:
    """Deterministic address stub from sha256(owner_id+asset_type)."""
    raw = f"{owner_id}{asset_type.value}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if asset_type in _ETH_LIKE:
        return f"0x{digest[:40]}"
    if asset_type in _BTC_LIKE:
        return f"1{digest[:33]}"
    return f"addr-{digest[:20]}"


class WalletManager:
    """Manages crypto wallet lifecycle."""

    def __init__(
        self,
        wallet_port: WalletPort | None = None,
        audit_port: AuditPort | None = None,
        agent: CryptoAgent | None = None,
    ) -> None:
        self._wallets: WalletPort = wallet_port or InMemoryWalletStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()
        self._agent: CryptoAgent = agent or CryptoAgent()

    def create_wallet(
        self,
        owner_id: str,
        asset_type: AssetType,
        wallet_type: str,
        network: NetworkType,
    ) -> WalletRecord:
        """Create a new wallet with deterministic address stub."""
        if wallet_type not in ("HOT", "COLD"):
            raise ValueError(f"Invalid wallet_type: {wallet_type}")
        wallet_id = f"wallet-{uuid.uuid4().hex[:12]}"
        address = _generate_address(owner_id, asset_type)
        now = datetime.utcnow()
        wallet = WalletRecord(
            id=wallet_id,
            asset_type=asset_type,
            status=WalletStatus.ACTIVE,
            address=address,
            balance=Decimal("0"),
            network=network,
            created_at=now,
            updated_at=now,
            owner_id=owner_id,
        )
        self._wallets.save_wallet(wallet)
        self._audit.log("CREATE_WALLET", wallet_id, f"owner={owner_id} type={wallet_type}", "OK")
        return wallet

    def get_balance(self, wallet_id: str) -> Decimal:
        """Get wallet balance (I-01: always Decimal)."""
        wallet = self._wallets.get_wallet(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        return wallet.balance

    def list_wallets(self, owner_id: str) -> list[WalletRecord]:
        return self._wallets.list_wallets(owner_id)

    def archive_wallet(self, wallet_id: str) -> HITLProposal:
        """Archive requires HITL (I-27)."""
        wallet = self._wallets.get_wallet(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        self._audit.log("ARCHIVE_WALLET", wallet_id, "HITL requested", "HITL_REQUIRED")
        return self._agent.process_archive_request(wallet_id)
