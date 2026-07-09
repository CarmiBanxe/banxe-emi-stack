"""runtime_gate — the ADR-030 §9 RED-agent activation gate (scaffold, PROPOSED).

Builds ONLY the missing §9 components (kill switch, budget policy, metrics/alert
hook, audit sampling, activation checklist). The DecisionRecord emission is REUSED
from `banxe.decision_records` (infra/clickhouse/migrations/006 + services/agents/
_lineage.py / recorders.py) — referenced, never rebuilt. Production adapters
(Temporal/Langfuse/PagerDuty) are Outcome-C stubs; InMemory is the sandbox default.
This scaffold activates NO agent capture.
"""

from __future__ import annotations

from .errors import (
    AgentHalted,
    AuditPolicyError,
    BudgetConfigError,
    KillSwitchUnavailable,
    OverBudget,
    RuntimeGateError,
)

__all__ = [
    "RuntimeGateError",
    "AgentHalted",
    "KillSwitchUnavailable",
    "BudgetConfigError",
    "OverBudget",
    "AuditPolicyError",
]
