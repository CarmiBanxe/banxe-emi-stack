"""
services/agent_routing/models.py — AgentTask data model
IL-ARL-01 | banxe-emi-stack

Normalized task envelope passed between gateway, tier workers, and swarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentTask:
    """Normalized task envelope for all LLM-requiring compliance events.

    Attributes:
        task_id:        UUID identifying this task instance.
        event_type:     Domain event name, e.g. "aml_screening", "kyc_check".
        tier:           Routing tier assigned by the gateway (1, 2, or 3).
        payload:        Domain-specific data dict (structured by event_type).
        product:        Product identifier, e.g. "sepa_retail_transfer".
        jurisdiction:   Regulatory jurisdiction, e.g. "EU", "UK".
        customer_id:    Customer identifier.
        risk_context:   Pre-computed risk signals from upstream services.
        created_at:     Task creation timestamp (UTC).
        playbook_id:    Playbook that matched this task.
        reasoning_hint: Reusable reasoning from ReasoningBank, if found.
    """

    task_id: str
    event_type: str
    tier: int
    payload: dict
    product: str
    jurisdiction: str
    customer_id: str
    risk_context: dict
    created_at: datetime
    playbook_id: str
    reasoning_hint: dict | None = field(default=None)

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"tier must be 1, 2 or 3; got {self.tier!r}")
        if not self.task_id:
            raise ValueError("task_id must not be empty")
        if not self.customer_id:
            raise ValueError("customer_id must not be empty")
