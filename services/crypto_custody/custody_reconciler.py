"""
services/crypto_custody/custody_reconciler.py — On-chain vs off-chain reconciliation
IL-CDC-01 | Phase 35 | banxe-emi-stack
I-01: All amounts Decimal. I-24: Audit trail append-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.crypto_custody.models import (
    AuditPort,
    InMemoryAuditStore,
    InMemoryOnChainStore,
    InMemoryWalletStore,
    OnChainPort,
    ReconciliationResult,
    WalletPort,
)

TOLERANCE_SATOSHI = Decimal("0.00000001")  # 1 satoshi


class CustodyReconciler:
    """Reconciles off-chain wallet records against on-chain balances."""

    def __init__(
        self,
        wallet_port: WalletPort | None = None,
        on_chain_port: OnChainPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._wallets: WalletPort = wallet_port or InMemoryWalletStore()
        self._on_chain: OnChainPort = on_chain_port or InMemoryOnChainStore()
        self._audit: AuditPort = audit_port or InMemoryAuditStore()

    def reconcile_wallet(self, wallet_id: str) -> ReconciliationResult:
        """Compare off-chain balance vs on-chain balance."""
        wallet = self._wallets.get_wallet(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet not found: {wallet_id}")
        on_chain = self._on_chain.get_balance(wallet.address, wallet.asset_type, wallet.network)
        off_chain = wallet.balance
        discrepancy = abs(on_chain - off_chain)
        status = "MATCHED" if discrepancy <= TOLERANCE_SATOSHI else "DISCREPANCY"
        result = ReconciliationResult(
            wallet_id=wallet_id,
            on_chain_balance=on_chain,
            off_chain_balance=off_chain,
            discrepancy=discrepancy,
            status=status,
            timestamp=datetime.now(UTC),
        )
        self._audit.log("RECONCILE", wallet_id, f"status={status}", "OK")
        return result

    def reconcile_all(self, owner_id: str) -> list[ReconciliationResult]:
        """Reconcile all wallets for an owner."""
        wallets = self._wallets.list_wallets(owner_id)
        return [self.reconcile_wallet(w.id) for w in wallets]

    def flag_discrepancy(self, result: ReconciliationResult) -> None:
        """Log discrepancy to audit trail (I-24 append-only)."""
        self._audit.log(
            "FLAG_DISCREPANCY",
            result.wallet_id,
            f"discrepancy={result.discrepancy} status={result.status}",
            "FLAGGED",
        )
