"""
wind_down_plan.py — Wind-Down Plan (WDP)
SP-THIN GAP-057 | FCA WDPG (Wind-Down Planning Guide) | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
The FCA Wind-Down Planning Guide (WDPG) requires firms to maintain a wind-down
plan: the triggers that would start an orderly wind-down, the financial runway
available, and the ordered steps to execute it. This complements the CASS 10A
resolution pack (`resolution_pack.py`, the post-event pack) with the FCA WDPG
planning view used BEFORE a resolution event.

FCA rules:
  - FCA WDPG: wind-down triggers, runway analysis, scenario steps
  - Amounts are GBP and ALWAYS Decimal (I-05)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


class TriggerType(str, Enum):
    CAPITAL = "CAPITAL"
    LIQUIDITY = "LIQUIDITY"
    CONDUCT = "CONDUCT"


@dataclass(frozen=True)
class WindDownTrigger:
    trigger_type: TriggerType
    metric: str
    current: Decimal
    threshold: Decimal
    breached: bool


@dataclass(frozen=True)
class WindDownFinancials:
    liquid_resources_gbp: Decimal
    monthly_wind_down_cost_gbp: Decimal
    own_funds_gbp: Decimal
    own_funds_requirement_gbp: Decimal
    liquidity_ratio: Decimal  # current liquidity coverage (1.4 = 140%)
    open_complaints_rate: Decimal  # conduct signal (0.0-1.0)


@dataclass(frozen=True)
class WindDownPlan:
    generated_at: datetime
    runway_months: Decimal
    triggers: list[WindDownTrigger]
    any_breach: bool
    steps: list[str]
    fca_guide: str = "FCA WDPG"


# Trigger thresholds (sandbox defaults; production calibrated via ICARA).
_MIN_CAPITAL_RATIO = Decimal("1.0")  # own funds >= requirement
_MIN_LIQUIDITY_RATIO = Decimal("1.0")
_MAX_COMPLAINTS_RATE = Decimal("0.05")

_WIND_DOWN_STEPS: tuple[str, ...] = (
    "Notify the FCA and invoke wind-down governance (board + senior management).",
    "Cease new customer onboarding; freeze new product issuance.",
    "Return safeguarded client money per the CASS 10A resolution pack.",
    "Settle outstanding payments and obligations from liquid resources.",
    "Run off existing contracts; transfer or terminate agreements.",
    "Final reconciliation, FSCS SCV production, and regulatory close-out.",
)


class WindDownPlanBuilder:
    """Evaluates wind-down triggers + runway and assembles the WDP."""

    def build(self, fin: WindDownFinancials) -> WindDownPlan:
        runway = (
            (fin.liquid_resources_gbp / fin.monthly_wind_down_cost_gbp).quantize(Decimal("0.1"))
            if fin.monthly_wind_down_cost_gbp > 0
            else Decimal("0")
        )
        capital_ratio = (
            (fin.own_funds_gbp / fin.own_funds_requirement_gbp).quantize(Decimal("0.01"))
            if fin.own_funds_requirement_gbp > 0
            else Decimal("0")
        )
        triggers = [
            WindDownTrigger(
                TriggerType.CAPITAL,
                "own_funds_ratio",
                capital_ratio,
                _MIN_CAPITAL_RATIO,
                capital_ratio < _MIN_CAPITAL_RATIO,
            ),
            WindDownTrigger(
                TriggerType.LIQUIDITY,
                "liquidity_ratio",
                fin.liquidity_ratio,
                _MIN_LIQUIDITY_RATIO,
                fin.liquidity_ratio < _MIN_LIQUIDITY_RATIO,
            ),
            WindDownTrigger(
                TriggerType.CONDUCT,
                "complaints_rate",
                fin.open_complaints_rate,
                _MAX_COMPLAINTS_RATE,
                fin.open_complaints_rate > _MAX_COMPLAINTS_RATE,
            ),
        ]
        return WindDownPlan(
            generated_at=datetime.now(UTC),
            runway_months=runway,
            triggers=triggers,
            any_breach=any(t.breached for t in triggers),
            steps=list(_WIND_DOWN_STEPS),
        )
