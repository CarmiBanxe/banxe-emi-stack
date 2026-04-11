"""
services/reasoning_bank/models.py — ReasoningBank data models
IL-ARL-01 | banxe-emi-stack

Entities for structured case memory and compliance decision storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CaseRecord:
    """Canonical snapshot of a compliance case at decision time.

    Attributes:
        case_id:        UUID for this case.
        event_type:     Source event type, e.g. "aml_screening".
        product:        Product at time of decision.
        jurisdiction:   Jurisdiction at time of decision.
        customer_id:    Customer identifier (pseudonymised for storage).
        risk_context:   Snapshot of risk signals that drove the decision.
        playbook_id:    Playbook version used.
        tier_used:      Tier that produced the final decision.
        created_at:     Case creation timestamp (UTC).
    """

    case_id: str
    event_type: str
    product: str
    jurisdiction: str
    customer_id: str
    risk_context: dict
    playbook_id: str
    tier_used: int
    created_at: datetime


@dataclass
class DecisionRecord:
    """Final compliance decision linked to a case."""

    decision_id: str
    case_id: str
    decision: str  # "approve", "decline", "manual_review", "hold"
    final_risk_score: float
    decided_by: str  # agent name or "human:MLRO"
    decided_at: datetime
    overridden: bool = False
    override_reason: str | None = None


@dataclass
class ReasoningRecord:
    """Structured reasoning chain stored in three views (GDPR Art.22)."""

    reasoning_id: str
    case_id: str
    internal_view: str  # Full technical reasoning for engineers
    audit_view: str  # Regulatory audit trail (MLR 2017)
    customer_view: str  # Plain-language explanation for customer
    token_cost: int
    model_used: str
    created_at: datetime


@dataclass
class EmbeddingRecord:
    """Vector embedding for similarity search."""

    embedding_id: str
    case_id: str
    vector: list[float]
    model_name: str
    dimension: int
    created_at: datetime


@dataclass
class PolicySnapshot:
    """Records which policy/playbook version governed a decision."""

    snapshot_id: str
    case_id: str
    playbook_id: str
    playbook_version: str
    policy_hash: str  # SHA-256 of playbook YAML at decision time
    captured_at: datetime


@dataclass
class FeedbackRecord:
    """Late outcome feedback — false positive, SAR filed, dispute (I-27).

    Write-only from this service; feedback_loop.py reads and proposes patches.
    """

    feedback_id: str
    case_id: str
    feedback_type: str  # "false_positive", "false_negative", "sar_filed", "dispute"
    provided_by: str  # "MLRO", "compliance_officer", "customer"
    note: str
    recorded_at: datetime
    applied_to_model: bool = False  # I-27: never auto-applied
