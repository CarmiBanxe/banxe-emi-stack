"""
services/fx_engine/fx_executor.py
FX Executor — Quote Execution
IL-FXE-01 | Sprint 34 | Phase 48

FCA: FCA COBS 14.3 (best execution), MLR 2017 Reg.28
Trust Zone: AMBER

L1 auto < £10k. HITLProposal ≥ £10k (I-04, I-27).
Append-only ExecutionStore (I-24). UTC timestamps (I-23).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
import uuid

from services.fx_engine.fx_quoter import FXQuoter
from services.fx_engine.models import (
    ExecutionStatus,
    FXExecution,
    HITLProposal,
    InMemoryExecutionStore,
    InMemoryQuoteStore,
    QuoteStatus,
    QuoteStore,
)
from services.fx_engine.models import ExecutionStore as ExecutionStoreProtocol

logger = logging.getLogger(__name__)

LARGE_FX_THRESHOLD = Decimal("10000")  # I-04 — requires HITL above this


class FXExecutor:
    """FX quote executor with HITL escalation for large amounts.

    L1 auto for sell_amount < £10k.
    L4 HITL for sell_amount >= £10k (I-04, I-27).
    Reject is always HITL L4 (I-27).
    Append-only execution log (I-24).
    """

    def __init__(
        self,
        quote_store: QuoteStore | None = None,
        execution_store: ExecutionStoreProtocol | None = None,
    ) -> None:
        """Initialise executor with optional stores."""
        self._quote_store: QuoteStore = quote_store or InMemoryQuoteStore()
        self._execution_store: ExecutionStoreProtocol = execution_store or InMemoryExecutionStore()
        self._quoter = FXQuoter(quote_store=self._quote_store)

    def execute(self, quote_id: str, actor: str) -> FXExecution | HITLProposal:
        """Execute an FX quote.

        I-04: sell_amount >= £10k → HITLProposal (I-27).
        I-24: appends to ExecutionStore.
        I-23: executed_at = UTC now.

        Args:
            quote_id: Quote to execute.
            actor: Actor requesting execution.

        Returns:
            FXExecution (confirmed or expired) or HITLProposal.
        """
        quote = self._quote_store.get(quote_id)
        if quote is None:
            execution = FXExecution(
                execution_id=f"exe_{uuid.uuid4().hex[:8]}",
                quote_id=quote_id,
                status=ExecutionStatus.REJECTED,
                rejection_reason="Quote not found",
            )
            self._execution_store.append(execution)
            return execution

        if not self._quoter.is_quote_valid(quote_id):
            execution = FXExecution(
                execution_id=f"exe_{uuid.uuid4().hex[:8]}",
                quote_id=quote_id,
                status=ExecutionStatus.EXPIRED,
            )
            self._execution_store.append(execution)  # I-24
            logger.info("Quote %s expired — cannot execute", quote_id)
            return execution

        if quote.sell_amount >= LARGE_FX_THRESHOLD:
            logger.warning(
                "Large FX execution %s amount=%s >= £10k — HITL required (I-04, I-27)",
                quote_id,
                quote.sell_amount,
            )
            return HITLProposal(
                action="EXECUTE_LARGE_FX",
                quote_id=quote_id,
                requires_approval_from="TREASURY_OPS",
                reason=f"FX execution {quote.sell_amount} {quote.sell_currency} >= £10k threshold (I-04)",
                autonomy_level="L4",
            )

        now = datetime.now(UTC).isoformat()
        execution = FXExecution(
            execution_id=f"exe_{uuid.uuid4().hex[:8]}",
            quote_id=quote_id,
            status=ExecutionStatus.CONFIRMED,
            executed_at=now,
            settlement_date=now,
            confirmation_ref=f"conf_{uuid.uuid4().hex[:6]}",
        )
        self._execution_store.append(execution)  # I-24
        updated_quote = quote.model_copy(update={"status": QuoteStatus.EXECUTED})
        self._quote_store.save(updated_quote)
        logger.info("Executed quote %s execution_id=%s", quote_id, execution.execution_id)
        return execution

    def reject(self, quote_id: str, reason: str, actor: str) -> HITLProposal:
        """Propose rejection of an FX quote (always L4 HITL, I-27).

        Rejection is always HITL — irreversible.

        Args:
            quote_id: Quote to reject.
            reason: Rejection reason.
            actor: Actor requesting rejection.

        Returns:
            HITLProposal for L4 human approval.
        """
        logger.warning(
            "Reject proposed for quote_id=%s by actor=%s reason=%s — HITL L4 (I-27)",
            quote_id,
            actor,
            reason,
        )
        return HITLProposal(
            action="REJECT_QUOTE",
            quote_id=quote_id,
            requires_approval_from="TREASURY_OPS",
            reason=f"Rejection by {actor}: {reason}",
            autonomy_level="L4",
        )

    def get_execution(self, execution_id: str) -> FXExecution | None:
        """Retrieve an execution by ID.

        Args:
            execution_id: Execution identifier.

        Returns:
            FXExecution or None.
        """
        return self._execution_store.get(execution_id)

    def get_executions_by_quote(self, quote_id: str) -> list[FXExecution]:
        """Get all executions for a quote.

        Args:
            quote_id: Quote identifier.

        Returns:
            List of FXExecution records.
        """
        return self._execution_store.list_by_quote(quote_id)
