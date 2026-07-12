"""
Banking Engine — Autonomy Level Enforcement
Sprint B-5 | I-27: AI PROPOSES, human DECIDES. EU AI Act Art.14.

L1 = Auto (low-risk, fully automated)
L2 = Alert → Human (acts but alerts; human reviews)
L3 = Auto + HITL gate (auto up to the gate; blocked at defined checkpoints)
L4 = Human Only (no AI action; only an authorised human may proceed)

check_autonomy() is the single enforcement point: call it before any
agent takes action above its own level.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Literal


class AutonomyLevel(IntEnum):
    """Agent autonomy levels — lower is more restricted."""

    L1 = 1  # Auto — fully automated, no human review
    L2 = 2  # Alert → Human — acts but alerts; human reviews
    L3 = 3  # Auto + HITL gate — blocked at defined gates
    L4 = 4  # Human Only — no AI action permitted


DecisionOutcome = Literal["ALLOW", "REQUIRE_HITL"]

_LEVEL_DESCRIPTIONS: dict[AutonomyLevel, str] = {
    AutonomyLevel.L1: "Auto — fully automated; no review needed.",
    AutonomyLevel.L2: "Alert → Human — AI acts but alerts; human reviews.",
    AutonomyLevel.L3: "Auto + HITL gate — blocked at compliance gates.",
    AutonomyLevel.L4: "Human Only — authorised human must act; no AI action.",
}


def check_autonomy(
    agent_level: AutonomyLevel,
    action_required_level: AutonomyLevel,
) -> DecisionOutcome:
    """
    Determine whether an agent may proceed autonomously.

    Returns "ALLOW" iff agent_level >= action_required_level.
    Returns "REQUIRE_HITL" otherwise — the caller must route to an HITL gate.

    I-27: Never returns ALLOW when action_required_level > agent_level.
    EU AI Act Art.14: Human oversight is mandatory for L3+ decisions.
    """
    if action_required_level > agent_level:
        return "REQUIRE_HITL"
    return "ALLOW"


def describe_level(level: AutonomyLevel) -> str:
    """Human-readable description of an autonomy level."""
    return _LEVEL_DESCRIPTIONS.get(level, f"Unknown level: {level}")
