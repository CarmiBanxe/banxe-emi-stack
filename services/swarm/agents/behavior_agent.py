"""
services/swarm/agents/behavior_agent.py — Behavioral Analysis Agent
IL-ARL-01 | banxe-emi-stack

Analyzes transaction patterns for behavioral anomalies:
amount spikes, velocity, time-of-day patterns, and cumulative risk.
"""

from __future__ import annotations

import logging
import time

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.swarm.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_VELOCITY_THRESHOLD = 10  # transactions in 24h
_AMOUNT_SPIKE_FACTOR = 3.0  # 3x average amount = spike
_HIGH_RISK_HOURS = frozenset(range(1, 6))  # 01:00–05:59 UTC


class BehaviorAgent(BaseAgent):
    """Transaction pattern and behavioral anomaly analysis."""

    @property
    def agent_name(self) -> str:
        return "behavior_agent"

    @property
    def signal_type(self) -> str:
        return "behavioral_anomaly"

    async def analyze(self, task: AgentTask) -> AgentResponse:
        t_start = time.monotonic()
        ctx = task.risk_context

        velocity_24h = int(ctx.get("velocity_24h", 0))
        amount_spike = ctx.get("amount_spike", False)
        cumulative_risk: float = ctx.get("cumulative_risk_score", 0.0)
        hour_utc = int(ctx.get("hour_utc", 12))
        structuring = ctx.get("structuring_detected", False)

        risk = cumulative_risk
        signals: list[str] = []

        if structuring:
            risk = min(risk + 0.4, 1.0)
            signals.append("structuring pattern detected (Tipping Off Act risk)")

        if velocity_24h >= _VELOCITY_THRESHOLD:
            risk = min(risk + 0.25, 1.0)
            signals.append(f"high velocity: {velocity_24h} transactions in 24h")

        if amount_spike:
            risk = min(risk + 0.3, 1.0)
            signals.append("amount spike vs. 30-day average")

        if hour_utc in _HIGH_RISK_HOURS:
            risk = min(risk + 0.1, 1.0)
            signals.append(f"off-hours transaction at {hour_utc:02d}:xx UTC")

        hint: str
        if risk >= 0.75:
            hint = "block"
        elif risk >= 0.45:
            hint = "warning"
        else:
            hint = "clear"

        summary = "; ".join(signals) if signals else "Normal behavioral pattern"

        return AgentResponse(
            agent_name=self.agent_name,
            case_id=task.task_id,
            signal_type=self.signal_type,
            risk_score=round(risk, 4),
            confidence=0.87,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=[f"velocity_check_{velocity_24h}"],
            token_cost=0,
            latency_ms=int((time.monotonic() - t_start) * 1000),
        )
