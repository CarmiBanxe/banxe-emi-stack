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
