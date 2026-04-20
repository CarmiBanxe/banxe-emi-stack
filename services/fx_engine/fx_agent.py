"""
services/fx_engine/fx_agent.py
FX Agent — HITL L4 Orchestration
IL-FXE-01 | Sprint 34 | Phase 48

FCA: FCA COBS 14.3, MLR 2017 Reg.28
Trust Zone: AMBER

L1 auto < £10k. L4 HITL >= £10k (I-04, I-27).
Reject/requote always HITL L4 (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging

from services.fx_engine.fx_quoter import FXQuoter

logger = logging.getLogger(__name__)

LARGE_FX_THRESHOLD = Decimal("10000")  # I-04


@dataclass
class HITLProposal:
    """HITL L4 escalation proposal for FX agent actions.

    FX executions >= £10k require TREASURY_OPS approval (I-04, I-27).
    Reject and requote always require L4 HITL.
    """

    action: str
    quote_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class FXAgent:
    """FX execution agent with tiered autonomy.

    L1 auto: sell_amount < £10k and quote valid.
    L4 HITL: sell_amount >= £10k, reject, or requote (I-04, I-27).
    """

    def __init__(self, quoter: FXQuoter | None = None) -> None:
        """Initialise agent with optional quoter."""
        self._quoter = quoter or FXQuoter()
        self._pending_executions: list[str] = []
        self._pending_rejects: list[str] = []
        self._pending_large_fx: list[str] = []

    def process_execute(
        self, quote_id: str, sell_amount: Decimal
    ) -> dict[str, object] | HITLProposal:
        """Process FX quote execution with tiered autonomy.

        I-04: L1 auto if sell_amount < £10k and quote valid.
        I-27: L4 HITL if sell_amount >= £10k.

        Args:
            quote_id: Quote to execute.
            sell_amount: Sell amount (Decimal, I-22).

        Returns:
            Auto-execution result dict (L1) or HITLProposal (L4).
        """
        if sell_amount >= LARGE_FX_THRESHOLD:
            self._pending_large_fx.append(quote_id)
            logger.warning(
                "Large FX %s amount=%s >= £10k — HITL L4 (I-04, I-27)", quote_id, sell_amount
            )
            return HITLProposal(
                action="EXECUTE_LARGE_FX",
                quote_id=quote_id,
                requires_approval_from="TREASURY_OPS",
                reason=f"FX execution {sell_amount} >= £10k threshold (I-04)",
                autonomy_level="L4",
            )

        if not self._quoter.is_quote_valid(quote_id):
            return {
                "quote_id": quote_id,
                "status": "EXPIRED",
                "autonomy_level": "L1",
                "message": "Quote expired — cannot auto-execute",
            }

        self._pending_executions.append(quote_id)
        logger.info("Auto-executing quote %s amount=%s (L1, I-04)", quote_id, sell_amount)
        return {
            "quote_id": quote_id,
            "status": "AUTO_APPROVED",
            "autonomy_level": "L1",
            "sell_amount": str(sell_amount),
            "message": "Auto-approved: amount < £10k threshold",
        }

    def process_reject(self, quote_id: str, reason: str) -> HITLProposal:
        """Propose FX quote rejection (always L4 HITL, I-27).

        Args:
            quote_id: Quote to reject.
            reason: Rejection reason.

        Returns:
            HITLProposal for L4 human approval.
        """
        self._pending_rejects.append(quote_id)
        logger.warning("Reject proposed quote_id=%s reason=%s — HITL L4 (I-27)", quote_id, reason)
        return HITLProposal(
            action="REJECT_QUOTE",
            quote_id=quote_id,
            requires_approval_from="TREASURY_OPS",
            reason=f"Rejection requested: {reason}",
            autonomy_level="L4",
        )

    def process_requote(self, currency_pair: str, sell_amount: Decimal) -> HITLProposal:
        """Propose FX requote (always L4 HITL, I-27).

        Requote is a new commitment — always requires HITL.

        Args:
            currency_pair: e.g. "GBP/EUR".
            sell_amount: Sell amount for new quote (Decimal, I-22).

        Returns:
            HITLProposal for L4 human approval.
        """
        logger.warning(
            "Requote proposed for %s amount=%s — HITL L4 (I-27)", currency_pair, sell_amount
        )
        return HITLProposal(
            action="REQUOTE",
            quote_id=currency_pair,
            requires_approval_from="TREASURY_OPS",
            reason=f"Requote {sell_amount} {currency_pair} — new commitment requires HITL",
            autonomy_level="L4",
        )

    def get_agent_status(self) -> dict[str, object]:
        """Get current agent status and pending queues.

        Returns:
            Dict with pending counts and autonomy levels.
        """
        return {
            "pending_executions": len(self._pending_executions),
            "pending_rejects": len(self._pending_rejects),
            "large_fx_pending": len(self._pending_large_fx),
            "autonomy_level": "L1/L4",
            "l1_threshold_gbp": str(LARGE_FX_THRESHOLD),
        }
