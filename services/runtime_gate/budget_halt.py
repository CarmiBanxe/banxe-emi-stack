"""Budget-halt seam (S-A2 C-2, ADR-047 + agent-budget-policy.md §2/§4).

Connects the existing fail-closed budget refusal (``BudgetManager.charge`` →
``OverBudget``) to the two obligations the refusal alone does not satisfy:

1. a durable decision-lineage record (ADR-046 §D4 — durable BEFORE the halt is
   surfaced) carrying ``budget_breach_flag=BREACH`` and the escalation target;
2. an entry in the agent's HITL escalation queue (``escalation_path`` from the
   governance table; agents never silently retry past a breach).

The halt is then re-raised as :class:`BudgetExceededError` — the public S-A2
name, a subclass of :class:`OverBudget` so every existing ``except OverBudget``
caller keeps working. If the recorder itself fails, the exception still
propagates: the agent halts either way (fail-closed, never fail-open).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
import uuid

from services.agents._lineage import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    DecisionRecorder,
)

from .budget import BudgetManager
from .errors import OverBudget

DEFAULT_ESCALATION_QUEUE = "human_review_queue"
HALT_ACTION = "HALT_BUDGET_EXCEEDED"


class BudgetExceededError(OverBudget):
    """Token/cost window exceeded — halted, lineage written, HITL enqueued."""


@dataclass(frozen=True)
class HitlEscalation:
    """One budget-halt escalation item (opaque metadata only — R-SEC)."""

    agent_id: str
    queue: str
    record_id: str
    reason: str


@runtime_checkable
class HitlQueuePort(Protocol):
    """Sink for budget-halt escalations (Protocol DI; production adapter later)."""

    async def enqueue(self, item: HitlEscalation) -> None: ...


class InMemoryHitlQueue:
    """Append-only in-process HITL queue stub (sandbox default)."""

    def __init__(self) -> None:
        self.items: list[HitlEscalation] = []

    async def enqueue(self, item: HitlEscalation) -> None:
        self.items.append(item)


class BudgetHaltGate:
    """Charge-or-halt wrapper around :class:`BudgetManager` (C-2 semantics)."""

    def __init__(
        self,
        manager: BudgetManager,
        recorder: DecisionRecorder,
        hitl: HitlQueuePort,
        escalation_paths: dict[str, str] | None = None,
    ) -> None:
        self._manager = manager
        self._recorder = recorder
        self._hitl = hitl
        self._paths = escalation_paths or {}

    async def charge(
        self,
        agent_id: str,
        tokens: int,
        cost: Decimal,
        *,
        intent: str,
        triggering_event: str,
        correlation_id: str,
    ) -> None:
        """Charge the window; on breach: lineage record → HITL enqueue → raise.

        Within-budget calls charge and return. ``BudgetConfigError`` (no policy)
        propagates unchanged — already fail-closed upstream.
        """
        try:
            self._manager.charge(agent_id, tokens, cost)
        except OverBudget as exc:
            queue = self._paths.get(agent_id, DEFAULT_ESCALATION_QUEUE)
            record = AgentDecisionRecord(
                record_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                agent_id=agent_id,
                triggering_event=triggering_event,
                intent=intent,
                policies_evaluated=["agent-budget-policy/v1", "ADR-047"],
                compliance_result=ComplianceResult.ESCALATE,
                reasoning_summary=f"budget halt: {exc}",
                confidence_score=1.0,
                action_taken=HALT_ACTION,
                human_reviewed_by=None,
                correlation_id=correlation_id,
                cost_tokens=tokens,
                cost_amount=cost,
                budget_window_ref=f"agent:{agent_id}",
                budget_breach_flag=BudgetBreach.BREACH,
                escalated_to=queue,
            )
            await self._recorder.record(record)
            await self._hitl.enqueue(
                HitlEscalation(
                    agent_id=agent_id,
                    queue=queue,
                    record_id=record.record_id,
                    reason=str(exc),
                )
            )
            raise BudgetExceededError(str(exc)) from exc


__all__ = [
    "DEFAULT_ESCALATION_QUEUE",
    "HALT_ACTION",
    "BudgetExceededError",
    "BudgetHaltGate",
    "HitlEscalation",
    "HitlQueuePort",
    "InMemoryHitlQueue",
]
