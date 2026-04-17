"""
services/crypto_custody/transfer_engine.py — Transfer initiation and execution
IL-CDC-01 | Phase 35 | banxe-emi-stack
I-27: Transfers >= £1000 always require HITL.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
import uuid

from services.crypto_custody.crypto_agent import CryptoAgent, HITLProposal
from services.crypto_custody.models import (
    AssetType,
    AuditPort,
    InMemoryAuditStore,
    InMemoryTransferStore,
    InMemoryWalletStore,
    TransferPort,
    TransferRecord,
    TransferStatus,
    WalletPort,
)

_HITL_THRESHOLD = Decimal("1000")


class TransferEngine:
    """Manages crypto transfer lifecycle."""

    def __init__(
        self,
        transfer_port: TransferPort | None = None,
        wallet_port: WalletPort | None = None,
        audit_port: AuditPort | None = None,
        agent: CryptoAgent | None = None,
    ) -> None:
        self._transfers: TransferPort = transfer_port or InMemoryTransferStore()
        self._wallets: WalletPort = wallet_port or InMemoryWalletStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()
        self._agent: CryptoAgent = agent or CryptoAgent()

    def initiate_transfer(
        self,
        from_wallet_id: str,
        to_address: str,
        amount: Decimal,
        asset_type: AssetType,
    ) -> TransferRecord:
        """Initiate a transfer (status=PENDING)."""
        if amount <= Decimal("0"):
            raise ValueError("Transfer amount must be positive (I-01)")
        wallet = self._wallets.get_wallet(from_wallet_id)
        if wallet is None:
            raise ValueError(f"Source wallet not found: {from_wallet_id}")
        transfer_id = f"txfr-{uuid.uuid4().hex[:12]}"
        transfer = TransferRecord(
            id=transfer_id,
            from_wallet_id=from_wallet_id,
            to_address=to_address,
            asset_type=asset_type,
            amount=amount,
            network_fee=Decimal("0"),
            status=TransferStatus.PENDING,
            travel_rule_required=amount >= _HITL_THRESHOLD,
            created_at=datetime.utcnow(),
        )
        self._transfers.save_transfer(transfer)
        self._audit.log("INITIATE_TRANSFER", transfer_id, f"amount={amount}", "PENDING")
        return transfer

    def validate_address(self, address: str, asset_type: AssetType) -> bool:
        """Basic format validation."""
        if asset_type == AssetType.BTC:
            return len(address) >= 25 and address[0] in ("1", "3", "b")
        if asset_type in (AssetType.ETH, AssetType.USDT, AssetType.USDC):
            return address.startswith("0x") and len(address) == 42
        return len(address) >= 10

    def execute_transfer(self, transfer_id: str) -> TransferRecord | HITLProposal:
        """Execute transfer — returns HITLProposal if amount >= £1000 (I-27)."""
        transfer = self._transfers.get_transfer(transfer_id)
        if transfer is None:
            raise ValueError(f"Transfer not found: {transfer_id}")
        result = self._agent.process_transfer_request(transfer_id, transfer.amount)
        if isinstance(result, HITLProposal):
            updated = dataclasses.replace(transfer, status=TransferStatus.HITL_REQUIRED)
            self._transfers.save_transfer(updated)
            self._audit.log("EXECUTE_TRANSFER", transfer_id, "HITL required", "HITL_REQUIRED")
            return result
        updated = dataclasses.replace(transfer, status=TransferStatus.EXECUTING)
        self._transfers.save_transfer(updated)
        self._audit.log("EXECUTE_TRANSFER", transfer_id, "auto-executing", "EXECUTING")
        return updated

    def confirm_on_chain(self, transfer_id: str, txhash: str) -> TransferRecord:
        """Confirm on-chain (status=CONFIRMED)."""
        transfer = self._transfers.get_transfer(transfer_id)
        if transfer is None:
            raise ValueError(f"Transfer not found: {transfer_id}")
        confirmed = dataclasses.replace(transfer, status=TransferStatus.CONFIRMED, txhash=txhash)
        self._transfers.save_transfer(confirmed)
        self._audit.log("CONFIRM_TRANSFER", transfer_id, f"txhash={txhash}", "CONFIRMED")
        return confirmed

    def reject_transfer(self, transfer_id: str, reason: str) -> TransferRecord:
        """Reject transfer (status=REJECTED)."""
        transfer = self._transfers.get_transfer(transfer_id)
        if transfer is None:
            raise ValueError(f"Transfer not found: {transfer_id}")
        rejected = dataclasses.replace(transfer, status=TransferStatus.REJECTED)
        self._transfers.save_transfer(rejected)
        self._audit.log("REJECT_TRANSFER", transfer_id, f"reason={reason}", "REJECTED")
        return rejected
