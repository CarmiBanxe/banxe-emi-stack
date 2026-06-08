"""L2 client-facing agents (ADR-049 Intent Layer & Client-Facing Agent Masks).

This package holds the banxe-emi-stack L2 client-facing agents that bind the
ADR-049 masks for capabilities owned by this repo's CONTRACT ports
(KYCProviderPort, NotificationProviderPort, CRMProviderPort). It is the
emi-stack analogue of banxe-payment-core's ``src/agents`` package, which holds
the Payments and FX/Exchange agents.

Each agent enforces, in the fixed ADR-049 §D2 gate-chain order
(process_ref → scope → band → cost_cap → compliance → step-up → port call),
the six mask fields (scope, autonomy_level, confirmation_policy, cost_cap,
lineage_obligation, compliance_gate) and emits exactly one
``AgentDecisionRecord`` (ADR-046) on every exit path. Ports and the lineage
recorder are injected as interfaces; agents never implement them.
"""

from __future__ import annotations

from services.agents._lineage import (
    AgentDecisionRecord,
    AgentOutcome,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    ProcessRef,
    RequestCost,
)
from services.agents.cards_agent import (
    BlockIntent,
    CardsAgent,
    CardsMask,
    ChangeLimitIntent,
    FreezeIntent,
    IssueCardIntent,
    ReadCardIntent,
    ReadLimitsIntent,
    UnfreezeIntent,
)
from services.agents.crm_agent import (
    ComplianceOverlay,
    CRMAgent,
    CRMMask,
    GetUserIntent,
    RegisterReferralIntent,
    ResolveCodeIntent,
    UpdateTierIntent,
)
from services.agents.notification_agent import (
    AutonomyLevel,
    ChannelCheckIntent,
    NotificationAgent,
    NotificationMask,
    NotificationSendIntent,
)

# NOTE: the agents share structurally-identical governance primitives (ProcessRef,
# RequestCost, CostCap, CostWindow, DecisionRecorder, ComplianceResult,
# ConfirmationDecision, BudgetBreach, AgentDecisionRecord, AgentOutcome). These now
# live in the canonical ``services/agents/_lineage.py`` module and are re-exported
# from here; each agent module imports the same single set (DRY — no per-module
# duplicates). The mask-specific public types (AutonomyLevel, ComplianceOverlay, the
# per-mask masks/intents) are re-exported from their owning agent module alongside.
__all__ = [
    "AgentDecisionRecord",
    "AgentOutcome",
    "AutonomyLevel",
    "BlockIntent",
    "BudgetBreach",
    "CRMAgent",
    "CRMMask",
    "CardsAgent",
    "CardsMask",
    "ChangeLimitIntent",
    "ChannelCheckIntent",
    "ComplianceOverlay",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "FreezeIntent",
    "GetUserIntent",
    "IssueCardIntent",
    "NotificationAgent",
    "NotificationMask",
    "NotificationSendIntent",
    "ProcessRef",
    "ReadCardIntent",
    "ReadLimitsIntent",
    "RegisterReferralIntent",
    "RequestCost",
    "ResolveCodeIntent",
    "UnfreezeIntent",
    "UpdateTierIntent",
]
