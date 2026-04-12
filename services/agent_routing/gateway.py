"""
services/agent_routing/gateway.py — Agent Gateway
IL-ARL-01 | banxe-emi-stack

Entry point for all LLM-requiring compliance events.
Normalizes domain events, assigns tiers, consults ReasoningBank,
and routes tasks to the appropriate tier worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import time
from typing import Any, Protocol
import uuid

from services.agent_routing.models import AgentTask
from services.agent_routing.playbook_engine import PlaybookEngine, PlaybookNotFoundError
from services.agent_routing.schemas import TierResult
from services.agent_routing.tier_workers import Tier1Worker, Tier2Worker, Tier3Worker

logger = logging.getLogger(__name__)


# ── Ports (Protocol DI) ───────────────────────────────────────────────────────


class ReasoningBankPort(Protocol):
    """Port for the ReasoningBank — find similar cases and retrieve reusable reasoning."""

    async def find_similar(
        self, event_type: str, risk_context: dict, top_k: int = 5
    ) -> list[dict]: ...

    async def get_reusable_reasoning(self, case_id: str) -> dict | None: ...


class TelemetryPort(Protocol):
    """Port for telemetry — emits routing metrics."""

    async def emit_routing_event(
        self,
        task_id: str,
        tier: int,
        event_type: str,
        product: str,
        jurisdiction: str,
        total_tokens: int,
        latency_ms: int,
        decision: str,
        reasoning_reused: bool,
    ) -> None: ...


class NullReasoningBank:
    """No-op ReasoningBank used when AGENT_ROUTING_ENABLED is false or bank unavailable."""

    async def find_similar(self, event_type: str, risk_context: dict, top_k: int = 5) -> list[dict]:
        return []

    async def get_reusable_reasoning(self, case_id: str) -> dict | None:
        return None


class NullTelemetry:
    """No-op telemetry used in tests or when ClickHouse is unavailable."""

    async def emit_routing_event(self, **_kwargs: Any) -> None:
        pass


# ── Agent Gateway ─────────────────────────────────────────────────────────────


class AgentGateway:
    """Entry point for all LLM-requiring compliance events.

    Responsibilities:
    - Normalize domain events into AgentTask format
    - Consult playbook for tier assignment
    - Query ReasoningBank for similar cases
    - Route to tier-specific worker
    - Emit telemetry after processing

    Usage::

        gateway = AgentGateway()
        result = await gateway.process(
            event_type="aml_screening",
            product="sepa_retail_transfer",
            jurisdiction="EU",
            customer_id="cust_123",
            payload={"amount_eur": 500, ...},
            risk_context={"known_beneficiary": True, ...},
        )
    """

    def __init__(
        self,
        playbook_engine: PlaybookEngine | None = None,
        reasoning_bank: ReasoningBankPort | None = None,
        telemetry: TelemetryPort | None = None,
    ) -> None:
        self._playbook_engine = playbook_engine or PlaybookEngine()
        self._reasoning_bank: ReasoningBankPort = reasoning_bank or NullReasoningBank()
        self._telemetry: TelemetryPort = telemetry or NullTelemetry()
        self._tier1 = Tier1Worker()
        self._tier2 = Tier2Worker()
        self._tier3 = Tier3Worker()

    # ── Public API ────────────────────────────────────────────────────────────

    async def process(
        self,
        event_type: str,
        product: str,
        jurisdiction: str,
        customer_id: str,
        payload: dict,
        risk_context: dict,
        task_id: str | None = None,
    ) -> TierResult:
        """Process a compliance event through the routing layer.

        Args:
            event_type:    Domain event name, e.g. "aml_screening".
            product:       Product identifier.
            jurisdiction:  Regulatory jurisdiction.
            customer_id:   Customer identifier.
            payload:       Domain-specific data.
            risk_context:  Pre-computed risk signals.
            task_id:       Optional explicit task UUID (generated if omitted).

        Returns:
            TierResult with final decision and metadata.
        """
        t_start = time.monotonic()
        task_id = task_id or str(uuid.uuid4())

        # Assign tier via playbook engine
        try:
            tier, playbook_id = self._playbook_engine.assign_tier(
                product=product,
                jurisdiction=jurisdiction,
                risk_context=risk_context,
            )
        except PlaybookNotFoundError:
            logger.warning(
                "No playbook for product=%r jurisdiction=%r — defaulting to Tier 3",
                product,
                jurisdiction,
            )
            tier, playbook_id = 3, "default_fallback"

        # Query ReasoningBank for reusable reasoning
        reasoning_hint: dict | None = None
        reasoning_reused = False
        similar_cases = await self._reasoning_bank.find_similar(
            event_type=event_type,
            risk_context=risk_context,
            top_k=3,
        )
        if similar_cases:
            reasoning_hint = await self._reasoning_bank.get_reusable_reasoning(
                similar_cases[0].get("case_id", "")
            )
            if reasoning_hint:
                reasoning_reused = True
                logger.debug("ReasoningBank cache hit for task %s", task_id)

        # Build the task envelope
        task = AgentTask(
            task_id=task_id,
            event_type=event_type,
            tier=tier,
            payload=payload,
            product=product,
            jurisdiction=jurisdiction,
            customer_id=customer_id,
            risk_context=risk_context,
            created_at=datetime.now(UTC),
            playbook_id=playbook_id,
            reasoning_hint=reasoning_hint,
        )

        # Route to the appropriate tier worker
        result = await self._route(task)
        result.reasoning_reused = reasoning_reused

        # Emit telemetry
        latency_ms = int((time.monotonic() - t_start) * 1000)
        result.total_latency_ms = latency_ms
        await self._telemetry.emit_routing_event(
            task_id=task_id,
            tier=tier,
            event_type=event_type,
            product=product,
            jurisdiction=jurisdiction,
            total_tokens=result.total_tokens,
            latency_ms=latency_ms,
            decision=result.decision,
            reasoning_reused=reasoning_reused,
        )
        return result

    def normalize_event(self, domain_event: dict[str, Any]) -> dict[str, Any]:
        """Extract standard routing fields from a raw domain event dict."""
        return {
            "event_type": domain_event.get("event_type", "unknown"),
            "product": domain_event.get("product", "unknown"),
            "jurisdiction": domain_event.get("jurisdiction", "unknown"),
            "customer_id": domain_event.get("customer_id", ""),
            "payload": domain_event.get("payload", {}),
            "risk_context": domain_event.get("risk_context", {}),
        }

    # ── Internal routing ──────────────────────────────────────────────────────

    async def _route(self, task: AgentTask) -> TierResult:
        match task.tier:
            case 1:
                return await self._tier1.process(task)
            case 2:
                return await self._tier2.process(task)
            case 3:
                return await self._tier3.process(task)
            case _:
                logger.error(
                    "Unknown tier %d for task %s — defaulting to Tier 3", task.tier, task.task_id
                )
                return await self._tier3.process(task)
