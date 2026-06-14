"""
services/intent_layer/canary.py — L1 Intent Layer canary auto-dispatch policy
FU-2 Phase 5 — staging canary (notifications only) | banxe-emi-stack

When the Intent Layer is enabled (see ``config.intent_layer_enabled``), this policy
decides — MECHANISTICALLY, in code, never via prompt — which resolved capabilities may
actually be auto-dispatched. It is the tightly-scoped gate that turns "the layer is on"
into "exactly one low-risk capability flows end-to-end" for the Phase-5 canary.

Two independent gates, checked in safety order:

  1. HIGH-RISK DENYLIST (hard, unconditional, non-configurable).
     Any capability touching money movement, FX, wallet/balance, cards, KYC/onboarding,
     SAR or sanctions/AML screening can NEVER be auto-dispatched in this phase. The
     denylist is matched on BOTH an explicit capability-key set AND a token scan over
     the capability label + matched intent, so a *newly added* or *mislabelled*
     high-risk capability is still caught. This gate wins even if such a capability is
     mistakenly added to the allowlist — it routes to the human/manual (governance)
     flow instead. (Guardrail: payments/FX/KYC/SAR/sanctions are never canary-dispatched.)

  2. CANARY ALLOWLIST (default-deny).
     ``INTENT_LAYER_CANARY_CAPABILITIES`` is a comma-separated list of capability keys
     permitted to auto-dispatch. EMPTY BY DEFAULT — so an enabled-but-unconfigured
     layer dispatches nothing (a leaked global flag in prod stays mechanically dark).
     For the staging canary it is set to ``Notifications`` only.

The policy is a pure value object: built from env at the composition root, then injected
into the router. It holds no I/O and is fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os

CANARY_CAPABILITIES_ENV = "INTENT_LAYER_CANARY_CAPABILITIES"


class CanaryDecision(str, Enum):
    """What the canary policy ruled for one resolved capability."""

    DISPATCH = "DISPATCH"  # allowlisted + not high-risk → auto-dispatch
    WITHHELD_NOT_CANARY = "WITHHELD_NOT_CANARY"  # enabled but not allowlisted → dark no-op
    WITHHELD_HIGH_RISK = "WITHHELD_HIGH_RISK"  # high-risk denylist → manual/governance flow


@dataclass(frozen=True)
class CanaryOutcome:
    """A canary decision plus an audit-legible reason (carried into logs/lineage)."""

    decision: CanaryDecision
    reason: str


def normalise_capability(capability: str) -> str:
    """Stable capability key: the lowercased lead token before any ``/`` or ``(``.

    Mirrors ``composition._cap_key`` so the allowlist/denylist key a capability the
    same way the dispatcher resolves its handler — ``"Notifications"`` → ``notifications``,
    ``"FX / Exchange"`` → ``fx``, ``"Analytics / Reporting (ADR-054)"`` → ``analytics``.
    """
    head = capability.split("(")[0].split("/")[0]
    return " ".join(head.lower().split())


# Explicit high-risk capability keys (normalised) — the canonical client capabilities
# that move money, touch wallets/cards, or run KYC/sanctions. Auto-dispatch of any of
# these is forbidden in the Phase-5 canary.
HIGH_RISK_CAPABILITY_KEYS: frozenset[str] = frozenset(
    {
        "payments",
        "fx",
        "wallet",
        "card",
        "kyc onboarding",
        "kyc",
        "sanctions",
        "sar",
        "aml",
    }
)

# Defence-in-depth token scan over (capability label + matched intent). Catches a NEW
# or mislabelled high-risk capability whose key is not yet in the explicit set above —
# e.g. "Cross-border payment", "Wire transfer", "Sanctions screening". Withholding is
# the safe direction, so an over-match merely routes to the manual flow.
HIGH_RISK_TOKENS: frozenset[str] = frozenset(
    {
        "payment",
        "fx",
        "exchange",
        "wallet",
        "balance",
        "transfer",
        "remit",
        "withdraw",
        "deposit",
        "card",
        "kyc",
        "onboard",
        "sanction",
        "screening",
        "sar",
        "aml",
        "swift",
        "sepa",
        "iban",
    }
)


def is_high_risk(capability: str, matched_intent: str | None = None) -> bool:
    """True if a capability must never be auto-dispatched in the canary phase.

    Belt-and-suspenders: an explicit normalised-key hit OR any high-risk token found in
    the capability label / matched intent. False-positives are safe (they withhold).
    """
    if normalise_capability(capability) in HIGH_RISK_CAPABILITY_KEYS:
        return True
    haystack = f"{capability} {matched_intent or ''}".lower()
    return any(token in haystack for token in HIGH_RISK_TOKENS)


def _parse_allowlist(raw: str) -> frozenset[str]:
    """Parse the comma-separated allowlist into normalised capability keys."""
    return frozenset(normalise_capability(item) for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class CanaryPolicy:
    """Pure policy object: decides auto-dispatch for one resolved capability.

    ``allowed_capabilities`` is the (already normalised) allowlist. The high-risk
    denylist is NOT a field — it is hard-coded module state, so it cannot be relaxed
    by configuration.
    """

    allowed_capabilities: frozenset[str]

    def decide(self, capability: str, matched_intent: str | None = None) -> CanaryOutcome:
        """Rule on one resolved capability. Assumes the layer is already enabled —
        the router checks enablement first; this gate only narrows *which* capabilities
        an enabled layer may dispatch."""
        if is_high_risk(capability, matched_intent):
            return CanaryOutcome(
                CanaryDecision.WITHHELD_HIGH_RISK,
                reason=(
                    f"capability {capability!r} is high-risk (money/FX/wallet/card/KYC/"
                    "SAR/sanctions) — never canary-dispatched; routed to human/manual flow"
                ),
            )
        if normalise_capability(capability) not in self.allowed_capabilities:
            return CanaryOutcome(
                CanaryDecision.WITHHELD_NOT_CANARY,
                reason=(
                    f"capability {capability!r} not in {CANARY_CAPABILITIES_ENV} allowlist "
                    "— no dispatch (dark-mode behaviour)"
                ),
            )
        return CanaryOutcome(
            CanaryDecision.DISPATCH,
            reason=f"capability {capability!r} is an allowlisted low-risk canary capability",
        )


def canary_policy_from_env(env: dict[str, str] | None = None) -> CanaryPolicy:
    """Build the canary policy from ``INTENT_LAYER_CANARY_CAPABILITIES`` (default empty)."""
    source = env if env is not None else os.environ
    return CanaryPolicy(
        allowed_capabilities=_parse_allowlist(source.get(CANARY_CAPABILITIES_ENV, ""))
    )


__all__ = [
    "CANARY_CAPABILITIES_ENV",
    "CanaryDecision",
    "CanaryOutcome",
    "CanaryPolicy",
    "HIGH_RISK_CAPABILITY_KEYS",
    "HIGH_RISK_TOKENS",
    "canary_policy_from_env",
    "is_high_risk",
    "normalise_capability",
]
