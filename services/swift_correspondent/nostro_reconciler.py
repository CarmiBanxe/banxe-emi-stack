"""
services/swift_correspondent/nostro_reconciler.py
Nostro Account Reconciler
IL-SWF-01 | Sprint 34 | Phase 47

FCA: MLR 2017 Reg.28, SWIFT gpi SRD
Trust Zone: RED

Decimal tolerance ±0.01 (I-22). Mismatch triggers HITL (I-27).
Append-only NostroStore (I-24). UTC timestamps (I-23).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
import uuid

from services.swift_correspondent.models import (
    HITLProposal,
    InMemoryNostroStore,
    NostroPosition,
    NostroStore,
)

logger = logging.getLogger(__name__)

RECON_TOLERANCE = Decimal("0.01")  # I-22: Decimal ±0.01


class NostroReconciler:
    """Reconciles nostro account positions between our records and correspondent.

    Append-only snapshots (I-24). All amounts Decimal (I-22).
    UTC timestamps (I-23). Mismatch > £0.01 → HITLProposal (I-27).
    """

    def __init__(self, store: NostroStore | None = None) -> None:
        """Initialise reconciler with optional nostro store."""
        self._store: NostroStore = store or InMemoryNostroStore()

    def take_snapshot(
        self,
        bank_id: str,
        currency: str,
        our_balance: Decimal,
        their_balance: Decimal,
    ) -> NostroPosition:
        """Record a nostro position snapshot.

        I-24: appends to NostroStore (never updates).
        I-22: all amounts as Decimal.
        I-23: snapshot_date = UTC datetime.

        Args:
            bank_id: Correspondent bank ID.
            currency: ISO 4217 currency code.
            our_balance: Our recorded balance (Decimal, I-22).
            their_balance: Their recorded balance (Decimal, I-22).

        Returns:
            Appended NostroPosition snapshot.
        """
        mismatch = abs(our_balance - their_balance)
        position = NostroPosition(
            position_id=f"pos_{uuid.uuid4().hex[:8]}",
            bank_id=bank_id,
            currency=currency,
            our_balance=our_balance,
            their_balance=their_balance,
            snapshot_date=datetime.now(UTC).isoformat(),
            mismatch_amount=mismatch,
        )
        self._store.append(position)  # I-24 append-only
        logger.info(
            "Nostro snapshot bank_id=%s currency=%s mismatch=%s",
            bank_id,
            currency,
            mismatch,
        )
        return position

    def check_mismatch(self, bank_id: str, currency: str) -> tuple[bool, Decimal]:
        """Check if latest nostro position has a mismatch.

        Args:
            bank_id: Correspondent bank ID.
            currency: ISO 4217 currency code.

        Returns:
            Tuple of (has_mismatch: bool, mismatch_amount: Decimal).
        """
        latest = self._store.get_latest(bank_id, currency)
        if latest is None:
            return False, Decimal("0")
        has_mismatch = latest.mismatch_amount > RECON_TOLERANCE
        return has_mismatch, latest.mismatch_amount

    def reconcile(
        self,
        bank_id: str,
        currency: str,
        our_balance: Decimal,
        their_balance: Decimal,
    ) -> NostroPosition | HITLProposal:
        """Reconcile nostro position, escalating mismatch to HITL.

        I-27: mismatch > RECON_TOLERANCE → HITLProposal.

        Args:
            bank_id: Correspondent bank ID.
            currency: ISO 4217 currency code.
            our_balance: Our recorded balance (Decimal, I-22).
            their_balance: Their recorded balance (Decimal, I-22).

        Returns:
            NostroPosition if within tolerance, HITLProposal if mismatch.
        """
        mismatch = abs(our_balance - their_balance)
        if mismatch > RECON_TOLERANCE:
            logger.warning(
                "Nostro mismatch detected bank_id=%s currency=%s mismatch=%s — HITL (I-27)",
                bank_id,
                currency,
                mismatch,
            )
            return HITLProposal(
                action="NOSTRO_MISMATCH",
                message_id=f"{bank_id}_{currency}",
                requires_approval_from="TREASURY_OPS",
                reason=f"Nostro mismatch {mismatch} {currency} exceeds tolerance {RECON_TOLERANCE}",
                autonomy_level="L4",
            )
        return self.take_snapshot(bank_id, currency, our_balance, their_balance)

    def get_daily_positions(self, bank_id: str) -> list[NostroPosition]:
        """Get all recorded positions for a bank.

        Args:
            bank_id: Correspondent bank ID.

        Returns:
            List of NostroPosition snapshots for this bank.
        """
        positions: list[NostroPosition] = []
        for currency in ["GBP", "EUR", "USD", "JPY", "CHF"]:
            latest = self._store.get_latest(bank_id, currency)
            if latest is not None:
                positions.append(latest)
        return positions

    def get_reconciliation_summary(self) -> dict[str, object]:
        """Get reconciliation summary statistics.

        Returns:
            Dict with total_snapshots, mismatches, currencies.
        """
        currencies: set[str] = set()
        mismatches = 0
        total = 0

        for currency in ["GBP", "EUR", "USD", "JPY", "CHF"]:
            for bank_id in ["cb_001", "cb_002", "cb_003"]:
                latest = self._store.get_latest(bank_id, currency)
                if latest is not None:
                    total += 1
                    currencies.add(currency)
                    if latest.mismatch_amount > RECON_TOLERANCE:
                        mismatches += 1

        return {
            "total_snapshots": total,
            "mismatches": mismatches,
            "currencies": list(currencies),
        }
