"""Runtime-gate errors. Every one is fail-closed: when it raises, the RED agent's
decision path refuses to act / cannot activate (deny-by-default)."""

from __future__ import annotations


class RuntimeGateError(Exception):
    """Base."""


class AgentHalted(RuntimeGateError):
    """Kill switch says HALTED (or the backend is unreachable ⇒ treated HALTED)."""


class KillSwitchUnavailable(RuntimeGateError):
    """Kill-switch backend could not be reached (fail-closed → HALTED)."""


class BudgetConfigError(RuntimeGateError):
    """Budget config absent / unparseable / no policy for the agent (fail-closed)."""


class OverBudget(RuntimeGateError):
    """Token/cost window exceeded — the agent refuses (blocked)."""


class AuditPolicyError(RuntimeGateError):
    """Audit sampler misconfigured, or a decision-ref carried PII/secret (R-SEC)."""
