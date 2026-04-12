"""
services/swarm/agents/profile_history_agent.py — Customer Profile History Agent
IL-ARL-01 | banxe-emi-stack

Analyzes customer account history, onboarding age, dispute history,
and previous compliance flags.
"""

from __future__ import annotations

import logging
import time

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.swarm.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_MIN_CUSTOMER_AGE_DAYS_TRUSTED = 90
_MAX_DISPUTE_COUNT = 2
_MAX_COMPLIANCE_FLAGS = 1


class ProfileHistoryAgent(BaseAgent):
    """Customer profile history and trust-level analysis."""

    @property
    def agent_name(self) -> str:
        return "profile_history_agent"

    @property
    def signal_type(self) -> str:
        return "profile_history"

    async def analyze(self, task: AgentTask) -> AgentResponse:
        t_start = time.monotonic()
        ctx = task.risk_context

        customer_age_days = int(ctx.get("customer_age_days", 0))
        dispute_count = int(ctx.get("dispute_count", 0))
        compliance_flags = int(ctx.get("compliance_flags", 0))
        kyc_level = ctx.get("kyc_level", "basic")
        previous_sar = ctx.get("previous_sar", False)

        risk = 0.0
        signals: list[str] = []
        evidence: list[str] = []

        if previous_sar:
            risk = min(risk + 0.5, 1.0)
            signals.append("customer has previous SAR filing")
            evidence.append("sar_history")

        if compliance_flags > _MAX_COMPLIANCE_FLAGS:
            risk = min(risk + 0.35, 1.0)
            signals.append(f"{compliance_flags} compliance flags on account")
            evidence.append("compliance_flag_history")

        if dispute_count > _MAX_DISPUTE_COUNT:
            risk = min(risk + 0.2, 1.0)
            signals.append(f"{dispute_count} past disputes")
            evidence.append("dispute_history")

        if customer_age_days < _MIN_CUSTOMER_AGE_DAYS_TRUSTED:
            age_risk = max(0.1, 0.3 - (customer_age_days / 300))
            risk = min(risk + age_risk, 1.0)
            signals.append(f"new customer: account age {customer_age_days} days")

        if kyc_level == "basic" and risk > 0.3:
            risk = min(risk + 0.15, 1.0)
            signals.append("basic KYC only — insufficient for elevated risk")

        hint: str
        if risk >= 0.75 or risk >= 0.4:
            hint = "warning"
        else:
            hint = "clear"

        summary = (
            "; ".join(signals)
            if signals
            else f"Clean profile, {customer_age_days} days old, {kyc_level} KYC"
        )

        return AgentResponse(
            agent_name=self.agent_name,
            case_id=task.task_id,
            signal_type=self.signal_type,
            risk_score=round(risk, 4),
            confidence=0.83,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=evidence,
            token_cost=0,
            latency_ms=int((time.monotonic() - t_start) * 1000),
        )
