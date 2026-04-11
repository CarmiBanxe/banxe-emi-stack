"""
services/swarm/orchestrator.py — Swarm Orchestrator
IL-ARL-01 | banxe-emi-stack

Launches and coordinates multiple specialized compliance agents.
Supports star, hierarchy, and ring topologies.
EU AI Act Art.14: Tier 3 decisions require human oversight (HITL).
"""

from __future__ import annotations

import asyncio
import logging
import time

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse, TierResult
from services.swarm.agents.base_agent import BaseAgent
from services.swarm.agents.behavior_agent import BehaviorAgent
from services.swarm.agents.geo_risk_agent import GeoRiskAgent
from services.swarm.agents.product_limits_agent import ProductLimitsAgent
from services.swarm.agents.profile_history_agent import ProfileHistoryAgent
from services.swarm.agents.sanctions_agent import SanctionsAgent

logger = logging.getLogger(__name__)

# ── Agent Registry ─────────────────────────────────────────────────────────────

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "sanctions": SanctionsAgent,
    "behavior": BehaviorAgent,
    "geo_risk": GeoRiskAgent,
    "profile_history": ProfileHistoryAgent,
    "product_limits": ProductLimitsAgent,
}


class UnknownTopologyError(Exception):
    """Raised when an unsupported topology is requested."""


class UnknownAgentError(Exception):
    """Raised when an agent name is not in the registry."""


# ── Swarm Orchestrator ────────────────────────────────────────────────────────


class SwarmOrchestrator:
    """Coordinates multiple specialized agents for Tier 3 complex cases.

    Topologies:
      star:      Independent parallel agents, deterministic aggregation.
      hierarchy: Coordinator (sanctions first) + subordinate agents.
      ring:      Sequential pipeline (e.g. sanctions → geo → profile → limits).

    Aggregation rules (deterministic first, LLM only for unresolved conflicts):
      - Any agent block + high confidence → hold
      - 3+ independent warnings above threshold → manual_review
      - All critical agents clear + risk < threshold → approve
    """

    def __init__(
        self,
        agent_registry: dict[str, type[BaseAgent]] | None = None,
        block_threshold: float = 0.85,
        warning_threshold: float = 0.45,
        approve_threshold: float = 0.25,
    ) -> None:
        self._registry = agent_registry or _AGENT_REGISTRY
        self._block_threshold = block_threshold
        self._warning_threshold = warning_threshold
        self._approve_threshold = approve_threshold

    # ── Public API ─────────────────────────────────────────────────────────────

    async def launch_swarm(
        self,
        task: AgentTask,
        topology: str,
        agent_names: list[str],
    ) -> TierResult:
        """Launch the swarm with the specified topology.

        Args:
            task:        The normalized AgentTask envelope.
            topology:    One of "star", "hierarchy", "ring".
            agent_names: List of agent registry keys to include.

        Returns:
            TierResult with aggregated decision.

        Raises:
            UnknownTopologyError: for unsupported topologies.
            UnknownAgentError: for unknown agent registry keys.
        """
        agents = self._instantiate_agents(agent_names)
        t_start = time.monotonic()

        match topology:
            case "star":
                responses = await self._star(task, agents)
            case "hierarchy":
                responses = await self._hierarchy(task, agents)
            case "ring":
                responses = await self._ring(task, agents)
            case _:
                raise UnknownTopologyError(f"Unsupported topology: {topology!r}")

        decision = self._aggregate(responses)
        total_tokens = sum(r.token_cost for r in responses)
        total_latency = int((time.monotonic() - t_start) * 1000)

        return TierResult(
            task_id=task.task_id,
            tier_used=3,
            decision=decision,
            responses=responses,
            total_tokens=total_tokens,
            total_latency_ms=total_latency,
            reasoning_reused=task.reasoning_hint is not None,
            playbook_version=task.playbook_id,
        )

    def list_agents(self) -> list[str]:
        """Return list of registered agent names."""
        return list(self._registry.keys())

    # ── Topologies ─────────────────────────────────────────────────────────────

    async def _star(self, task: AgentTask, agents: list[BaseAgent]) -> list[AgentResponse]:
        """Parallel independent agents — fastest, best for AML triage."""
        tasks = [agent.analyze(task) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        responses: list[AgentResponse] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_name = agents[i].agent_name
                logger.error("Agent %s failed: %s", agent_name, result)
                # Include a fallback manual_review response on agent failure
                responses.append(
                    AgentResponse(
                        agent_name=agent_name,
                        case_id=task.task_id,
                        signal_type=agents[i].signal_type,
                        risk_score=0.5,
                        confidence=0.1,
                        decision_hint="manual_review",
                        reason_summary=f"Agent failed: {result}",
                        evidence_refs=[],
                        token_cost=0,
                        latency_ms=0,
                    )
                )
            else:
                responses.append(result)  # type: ignore[arg-type]
        return responses

    async def _hierarchy(self, task: AgentTask, agents: list[BaseAgent]) -> list[AgentResponse]:
        """Coordinator (first agent) + parallel subordinates.

        If the coordinator returns block, subordinates are skipped.
        """
        if not agents:
            return []
        coordinator = agents[0]
        coordinator_resp = await coordinator.analyze(task)
        responses = [coordinator_resp]

        # Early-exit on coordinator block
        if (
            coordinator_resp.decision_hint == "block"
            and coordinator_resp.confidence >= self._block_threshold
        ):
            logger.info(
                "Coordinator %s returned block with confidence %.2f — skipping subordinates",
                coordinator.agent_name,
                coordinator_resp.confidence,
            )
            return responses

        # Run subordinates in parallel
        subordinates = agents[1:]
        sub_responses = await self._star(task, subordinates)
        responses.extend(sub_responses)
        return responses

    async def _ring(self, task: AgentTask, agents: list[BaseAgent]) -> list[AgentResponse]:
        """Sequential pipeline — each agent runs after the previous.

        Use for KYC flows: docs → profile → PEP/sanctions.
        Short-circuits on block.
        """
        responses: list[AgentResponse] = []
        for agent in agents:
            try:
                resp = await agent.analyze(task)
            except Exception as exc:
                logger.error("Ring agent %s failed: %s", agent.agent_name, exc)
                resp = AgentResponse(
                    agent_name=agent.agent_name,
                    case_id=task.task_id,
                    signal_type=agent.signal_type,
                    risk_score=0.5,
                    confidence=0.1,
                    decision_hint="manual_review",
                    reason_summary=f"Agent failed: {exc}",
                    evidence_refs=[],
                    token_cost=0,
                    latency_ms=0,
                )
            responses.append(resp)
            # Short-circuit on high-confidence block
            if resp.decision_hint == "block" and resp.confidence >= self._block_threshold:
                logger.info(
                    "Ring short-circuit at agent %s (block + confidence %.2f)",
                    agent.agent_name,
                    resp.confidence,
                )
                break
        return responses

    # ── Aggregation ────────────────────────────────────────────────────────────

    def _aggregate(self, responses: list[AgentResponse]) -> str:
        """Deterministic aggregation — LLM only for unresolved Tier 3 conflicts."""
        if not responses:
            return "manual_review"

        # Rule 1: any block with high confidence → hold
        high_conf_blocks = [
            r
            for r in responses
            if r.decision_hint == "block" and r.confidence >= self._block_threshold
        ]
        if high_conf_blocks:
            return "hold"

        # Rule 2: any block (lower confidence) → decline
        any_block = any(r.decision_hint == "block" for r in responses)
        if any_block:
            return "decline"

        # Rule 3: 3+ independent warnings above threshold → manual_review
        high_conf_warnings = [
            r
            for r in responses
            if r.decision_hint == "warning" and r.confidence >= self._warning_threshold
        ]
        if len(high_conf_warnings) >= 3:
            return "manual_review"

        # Rule 4: all critical agents clear + risk < approve_threshold → approve
        max_risk = max((r.risk_score for r in responses), default=0.0)
        if max_risk < self._approve_threshold:
            return "approve"

        # Rule 5: moderate risk → manual_review
        if max_risk < 0.6:
            return "manual_review"

        # Rule 6: high risk → decline
        return "decline"

    # ── Internal ───────────────────────────────────────────────────────────────

    def _instantiate_agents(self, agent_names: list[str]) -> list[BaseAgent]:
        """Instantiate agents from the registry."""
        agents: list[BaseAgent] = []
        for name in agent_names:
            agent_cls = self._registry.get(name)
            if agent_cls is None:
                raise UnknownAgentError(
                    f"Agent {name!r} not in registry. Available: {list(self._registry.keys())}"
                )
            agents.append(agent_cls())
        return agents
