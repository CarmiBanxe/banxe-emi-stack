"""
services/agent_routing/policy_engine.py — Policy Engine
IL-ARL-01 | banxe-emi-stack

Controls token budgets, tier auto-downgrade under budget pressure,
feature flags for swarm/background workers, and LLM fallback.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when a tier's hourly token budget is exhausted."""


@dataclass
class TierBudget:
    """Per-tier hourly token budget tracking."""

    tier: int
    limit_tokens_per_hour: int
    used_tokens: int = 0
    window_start: datetime = field(default_factory=lambda: datetime.now(UTC))

    def consume(self, tokens: int) -> None:
        """Record token consumption, resetting window if needed."""
        now = datetime.now(UTC)
        if (now - self.window_start) >= timedelta(hours=1):
            self.used_tokens = 0
            self.window_start = now
        self.used_tokens += tokens

    @property
    def remaining(self) -> int:
        """Tokens remaining in the current window."""
        return max(0, self.limit_tokens_per_hour - self.used_tokens)

    @property
    def is_exhausted(self) -> bool:
        return self.remaining == 0


@dataclass
class PolicyConfig:
    """Runtime policy configuration loaded from environment."""

    # Feature flags
    agent_routing_enabled: bool = True
    swarm_enabled: bool = True
    reasoning_bank_enabled: bool = True
    background_workers_enabled: bool = True

    # Token budget limits per tier per hour
    tier1_budget_per_hour: int = 0  # rule-only, unlimited
    tier2_budget_per_hour: int = 500_000
    tier3_budget_per_hour: int = 100_000

    # Auto-downgrade thresholds (% of budget consumed)
    auto_downgrade_threshold: float = 0.85

    # Fallback config
    llm_fallback_to_rules: bool = True

    @classmethod
    def from_env(cls) -> PolicyConfig:
        """Load config from environment variables."""
        return cls(
            agent_routing_enabled=os.environ.get("AGENT_ROUTING_ENABLED", "false").lower()
            == "true",
            swarm_enabled=os.environ.get("SWARM_ENABLED", "true").lower() == "true",
            reasoning_bank_enabled=os.environ.get("REASONING_BANK_ENABLED", "true").lower()
            == "true",
            background_workers_enabled=os.environ.get("BACKGROUND_WORKERS_ENABLED", "true").lower()
            == "true",
            tier2_budget_per_hour=int(os.environ.get("TIER2_BUDGET_TOKENS_PER_HOUR", "500000")),
            tier3_budget_per_hour=int(os.environ.get("TIER3_BUDGET_TOKENS_PER_HOUR", "100000")),
            auto_downgrade_threshold=float(os.environ.get("AUTO_DOWNGRADE_THRESHOLD", "0.85")),
            llm_fallback_to_rules=os.environ.get("LLM_FALLBACK_TO_RULES", "true").lower() == "true",
        )


class PolicyEngine:
    """Controls routing policy, token budgets, and fallback behaviour.

    Usage::

        engine = PolicyEngine()
        effective_tier = engine.effective_tier(requested_tier=3, risk_score=0.3)
        engine.consume_budget(tier=2, tokens=500)
    """

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self._config = config or PolicyConfig.from_env()
        self._budgets: dict[int, TierBudget] = {
            1: TierBudget(tier=1, limit_tokens_per_hour=0),
            2: TierBudget(tier=2, limit_tokens_per_hour=self._config.tier2_budget_per_hour),
            3: TierBudget(tier=3, limit_tokens_per_hour=self._config.tier3_budget_per_hour),
        }

    # ── Feature flags ──────────────────────────────────────────────────────────

    @property
    def routing_enabled(self) -> bool:
        return self._config.agent_routing_enabled

    @property
    def swarm_enabled(self) -> bool:
        return self._config.swarm_enabled and self._config.agent_routing_enabled

    @property
    def reasoning_bank_enabled(self) -> bool:
        return self._config.reasoning_bank_enabled

    # ── Budget management ──────────────────────────────────────────────────────

    def consume_budget(self, tier: int, tokens: int) -> None:
        """Record token consumption for a tier."""
        if tier in self._budgets:
            self._budgets[tier].consume(tokens)

    def budget_remaining(self, tier: int) -> int:
        """Return remaining tokens for a tier in the current window."""
        budget = self._budgets.get(tier)
        return budget.remaining if budget else 0

    def is_budget_exhausted(self, tier: int) -> bool:
        """Check if a tier's budget is exhausted."""
        budget = self._budgets.get(tier)
        return budget.is_exhausted if budget else False

    def budget_pressure(self, tier: int) -> float:
        """Return budget pressure ratio 0.0–1.0 (1.0 = fully consumed)."""
        budget = self._budgets.get(tier)
        if budget is None or budget.limit_tokens_per_hour == 0:
            return 0.0
        return budget.used_tokens / budget.limit_tokens_per_hour

    # ── Tier downgrade ─────────────────────────────────────────────────────────

    def effective_tier(self, requested_tier: int, risk_score: float = 0.0) -> int:
        """Determine effective tier considering budget pressure and feature flags.

        Auto-downgrades low-risk tasks from Tier 3 → Tier 2 or Tier 2 → Tier 1
        when budget pressure exceeds the configured threshold.

        High-risk tasks (risk_score >= 0.75) are NEVER downgraded.

        Args:
            requested_tier: Tier assigned by PlaybookEngine.
            risk_score:     Current cumulative risk score (0.0–1.0).

        Returns:
            Effective tier to use (may be lower than requested).
        """
        # Never downgrade high-risk cases
        if risk_score >= 0.75:
            return requested_tier

        tier = requested_tier
        for _ in range(2):  # allow at most 2 downgrade steps
            if tier <= 1:
                break
            pressure = self.budget_pressure(tier)
            if pressure >= self._config.auto_downgrade_threshold:
                logger.warning(
                    "Tier %d budget pressure %.0f%% >= threshold %.0f%% — auto-downgrading",
                    tier,
                    pressure * 100,
                    self._config.auto_downgrade_threshold * 100,
                )
                tier -= 1
            else:
                break
        return tier

    # ── LLM fallback ───────────────────────────────────────────────────────────

    def should_fallback_to_rules(self, tier: int) -> bool:
        """Return True if tier should fall back to rule-only mode.

        Fallback is triggered when:
        - LLM is unavailable (flag llm_fallback_to_rules=True)
        - Budget is exhausted for this tier
        """
        if not self._config.llm_fallback_to_rules:
            return False
        return self.is_budget_exhausted(tier)

    # ── Config introspection ───────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a snapshot of current policy state for telemetry/debug."""
        return {
            "routing_enabled": self.routing_enabled,
            "swarm_enabled": self.swarm_enabled,
            "reasoning_bank_enabled": self.reasoning_bank_enabled,
            "budgets": {
                tier: {
                    "used": b.used_tokens,
                    "limit": b.limit_tokens_per_hour,
                    "remaining": b.remaining,
                    "pressure": self.budget_pressure(tier),
                }
                for tier, b in self._budgets.items()
            },
        }
