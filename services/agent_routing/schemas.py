"""
services/agent_routing/schemas.py — AgentResponse and TierResult schemas
IL-ARL-01 | banxe-emi-stack

Unified response structures returned by tier workers and the swarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResponse:
    """Unified response from any tier or specialized agent.

    Attributes:
        agent_name:     Name of the agent that produced this response.
        case_id:        Correlation ID linking response to the original task.
        signal_type:    The compliance signal assessed, e.g. "sanctions_screening".
        risk_score:     Normalised risk score 0.0 (clean) to 1.0 (highest risk).
        confidence:     Confidence in the risk score (0.0–1.0).
        decision_hint:  One of: "clear", "warning", "block", "manual_review".
        reason_summary: Human-readable explanation of the decision.
        evidence_refs:  References to evidence records (IDs, log entries, etc.).
        token_cost:     Tokens consumed to produce this response (0 for rule-only).
        latency_ms:     Wall-clock latency in milliseconds.
    """

    agent_name: str
    case_id: str
    signal_type: str
    risk_score: float
    confidence: float
    decision_hint: str
    reason_summary: str
    evidence_refs: list[str]
    token_cost: int
    latency_ms: int

    _VALID_HINTS: frozenset[str] = field(
        default_factory=lambda: frozenset({"clear", "warning", "block", "manual_review"}),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError(f"risk_score must be 0.0–1.0; got {self.risk_score}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0–1.0; got {self.confidence}")
        valid = {"clear", "warning", "block", "manual_review"}
        if self.decision_hint not in valid:
            raise ValueError(f"decision_hint must be one of {valid}; got {self.decision_hint!r}")
        if self.token_cost < 0:
            raise ValueError("token_cost must be >= 0")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")


@dataclass
class TierResult:
    """Final routing decision produced after tier processing.

    Attributes:
        task_id:            Original task UUID.
        tier_used:          Which tier processed the task (1, 2, or 3).
        decision:           Final decision: "approve", "decline", "manual_review", "hold".
        responses:          All AgentResponse objects that contributed to this decision.
        total_tokens:       Total tokens consumed across all agents.
        total_latency_ms:   End-to-end wall-clock latency.
        reasoning_reused:   True if ReasoningBank cache was used.
        playbook_version:   Playbook identifier and version that governed routing.
    """

    task_id: str
    tier_used: int
    decision: str
    responses: list[AgentResponse]
    total_tokens: int
    total_latency_ms: int
    reasoning_reused: bool
    playbook_version: str

    _VALID_DECISIONS: frozenset[str] = field(
        default_factory=lambda: frozenset({"approve", "decline", "manual_review", "hold"}),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        valid = {"approve", "decline", "manual_review", "hold"}
        if self.decision not in valid:
            raise ValueError(f"decision must be one of {valid}; got {self.decision!r}")
        if self.tier_used not in (1, 2, 3):
            raise ValueError(f"tier_used must be 1, 2 or 3; got {self.tier_used}")
