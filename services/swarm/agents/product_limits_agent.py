"""
services/swarm/agents/product_limits_agent.py — Product Limits Agent
IL-ARL-01 | banxe-emi-stack

Validates transaction amounts against product-specific limits
and EDD thresholds per CASS 7.15 and MLR 2017.
"""

from __future__ import annotations

from decimal import Decimal
import logging
import time

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.swarm.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Product-specific limits (EUR) — in production load from config/database
_PRODUCT_LIMITS: dict[str, dict] = {
    "sepa_retail_transfer": {
        "single_max_eur": Decimal("50000"),
        "daily_max_eur": Decimal("100000"),
        "monthly_max_eur": Decimal("500000"),
    },
    "fps_retail_transfer": {
        "single_max_eur": Decimal("25000"),
        "daily_max_eur": Decimal("50000"),
        "monthly_max_eur": Decimal("250000"),
    },
    "default": {
        "single_max_eur": Decimal("10000"),
        "daily_max_eur": Decimal("25000"),
        "monthly_max_eur": Decimal("100000"),
    },
}

# I-04: EDD thresholds
_EDD_INDIVIDUAL = Decimal("10000")
_EDD_CORPORATE = Decimal("50000")


class ProductLimitsAgent(BaseAgent):
    """Product-specific transaction limit and EDD threshold validation."""

    @property
    def agent_name(self) -> str:
        return "product_limits_agent"

    @property
    def signal_type(self) -> str:
        return "product_limits"

    async def analyze(self, task: AgentTask) -> AgentResponse:
        t_start = time.monotonic()
        ctx = task.risk_context
        payload = task.payload

        # Use Decimal for all monetary comparisons (I-01)
        amount_str = str(payload.get("amount_eur", ctx.get("amount_eur", "0")))
        amount = Decimal(amount_str)

        product = task.product
        limits = _PRODUCT_LIMITS.get(product, _PRODUCT_LIMITS["default"])
        single_max = limits["single_max_eur"]

        customer_type = ctx.get("customer_type", "individual")
        edd_threshold = _EDD_CORPORATE if customer_type == "corporate" else _EDD_INDIVIDUAL

        daily_total = Decimal(str(ctx.get("daily_total_eur", "0")))
        monthly_total = Decimal(str(ctx.get("monthly_total_eur", "0")))

        signals: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        if amount > single_max:
            risk = min(risk + 0.7, 1.0)
            signals.append(f"Amount {amount} EUR exceeds single-transaction limit {single_max}")
            evidence.append(f"product_limit_{product}")

        elif amount > edd_threshold:
            risk = min(risk + 0.5, 1.0)
            signals.append(f"Amount {amount} EUR exceeds EDD threshold {edd_threshold} (I-04)")
            evidence.append("invariant_I-04")

        if daily_total + amount > limits["daily_max_eur"]:
            risk = min(risk + 0.4, 1.0)
            signals.append(
                f"Daily total {daily_total + amount} EUR exceeds daily limit {limits['daily_max_eur']}"
            )
            evidence.append("daily_limit_check")

        if monthly_total + amount > limits["monthly_max_eur"]:
            risk = min(risk + 0.3, 1.0)
            signals.append(f"Monthly total would exceed limit {limits['monthly_max_eur']} EUR")
            evidence.append("monthly_limit_check")

        hint: str
        if risk >= 0.7:
            hint = "block"
        elif risk >= 0.4:
            hint = "warning"
        else:
            hint = "clear"

        summary = (
            "; ".join(signals) if signals else f"Amount {amount} EUR within all product limits"
        )

        return AgentResponse(
            agent_name=self.agent_name,
            case_id=task.task_id,
            signal_type=self.signal_type,
            risk_score=round(risk, 4),
            confidence=1.0,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=evidence,
            token_cost=0,
            latency_ms=int((time.monotonic() - t_start) * 1000),
        )
