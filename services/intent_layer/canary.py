"""
services/intent_layer/canary.py — L1 Intent Layer canary SCOPE + hard guardrails (FU-2 Phase 7).

Phase 5/6 stood up a Notifications-only canary in staging behind
``INTENT_LAYER_ENABLED`` and instrumented it (``observability.py``). Phase 7 widens
that canary by ONE low-risk capability (Referral / CRM) and makes the *scope itself*
explicit, env-bound and fail-closed:

  * ``INTENT_LAYER_CANARY_CAPABILITIES`` — a comma-separated allow-list of capability
    labels the canary may dispatch in staging (default: Notifications only, i.e. the
    Phase 6 state). It is honoured **only when ``BANXE_ENV == staging``**; in any other
    environment the effective allow-list is empty, so a flag leaked to prod cannot
    widen the canary. This is the mechanical proof behind "non-staging stays dark".

  * ``HIGH_RISK_CAPABILITY_KEYS`` / ``HIGH_RISK_TOKENS`` — a hard, code-level denylist
    of money/FX/wallet/card/KYC/SAR/sanctions surfaces. It is subtracted from the
    effective allow-list (so a misconfigured ``INTENT_LAYER_CANARY_CAPABILITIES`` that
    lists "Payments" silently drops it) AND enforced again at the dispatch boundary
    (``composition.CapabilityDispatcher``) as defense-in-depth — a high-risk capability
    can never be dispatched by the canary even if both the allow-list and a handler were
    misconfigured to include it.

This module is PURE (no agent / port imports), so the classifier/router stay
unit-testable in isolation; the env read is injectable for deterministic tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os

CANARY_CAPABILITIES_ENV = "INTENT_LAYER_CANARY_CAPABILITIES"
BANXE_ENV_ENV = "BANXE_ENV"
STAGING_ENV_VALUE = "staging"

# The Phase 6 default scope: Notifications only. Widening to anything else is an
# explicit opt-in via INTENT_LAYER_CANARY_CAPABILITIES (set in the staging config),
# so a fresh/unset environment never silently dispatches a wider surface.
DEFAULT_CANARY_CAPABILITIES: tuple[str, ...] = ("Notifications",)

# Hard denylist — NORMALISED capability keys that the canary must NEVER dispatch,
# regardless of configuration. These are the money-moving / regulated surfaces
# (ADR-049 §D3): payments, FX, wallet/balance, cards, KYC onboarding.
HIGH_RISK_CAPABILITY_KEYS: frozenset[str] = frozenset(
    {
        "payments",
        "fx",
        "wallet",
        "card",
        "kyc onboarding",
    }
)

# Hard denylist — substrings that, if present anywhere in a capability label or key,
# force a high-risk classification. This catches mis-typed / adjacent labels (e.g.
# "Card (Wallet/Payments-adjacent)", "Sanctions screening", "SAR filing", "AML review")
# even when they are not an exact key match. Kept deliberately specific so the
# low-risk canary surfaces (Notifications, Referral / CRM, Support, Statements,
# Analytics) contain none of these substrings.
HIGH_RISK_TOKENS: frozenset[str] = frozenset(
    {
        "payment",
        "fx",
        "exchange",
        "wallet",
        "balance",
        "card",
        "kyc",
        "onboard",
        "sanction",
        "sar",
        "aml",
        "transfer",
        "withdraw",
        "deposit",
        "money",
        "fund",
        "swift",
        "iban",
    }
)


def normalize_capability(capability: str) -> str:
    """Normalise a catalogue capability label to a stable registry key.

    Catalogue labels carry adornments (``"Analytics / Reporting (ADR-054)"``); the key
    is the lowercased lead token before any ``/`` or ``(`` — so ``"Notifications"`` →
    ``"notifications"``, ``"Referral / CRM"`` → ``"referral"`` and the example above →
    ``"analytics"``. This is the single source of truth for the key shape; the L1→L2
    dispatcher reuses it so handler registration and gating never diverge.
    """
    head = capability.split("(")[0].split("/")[0]
    return " ".join(head.lower().split())


def is_high_risk_capability(capability: str) -> bool:
    """True when a capability is a money/FX/wallet/card/KYC/SAR/sanctions surface.

    Fail-closed by design: an exact key match OR any high-risk token substring (checked
    against both the lowercased raw label and the normalised key) marks it high-risk.
    Used to subtract high-risk entries from the canary allow-list AND as the hard
    dispatch-boundary backstop (defense-in-depth)."""
    key = normalize_capability(capability)
    if key in HIGH_RISK_CAPABILITY_KEYS:
        return True
    label = capability.strip().lower()
    return any(token in label or token in key for token in HIGH_RISK_TOKENS)


def canary_env(env: dict[str, str] | None = None) -> str:
    """Deployment label gating the canary scope. Reads ``BANXE_ENV`` (e.g. ``staging``);
    unknown/blank → ``"unknown"`` (a non-staging value, so the canary stays narrow)."""
    source = env if env is not None else os.environ
    return (source.get(BANXE_ENV_ENV) or "unknown").strip().lower() or "unknown"


def parse_canary_capabilities(raw: str | None) -> tuple[str, ...]:
    """Parse the comma-separated ``INTENT_LAYER_CANARY_CAPABILITIES`` value into labels.

    ``None`` (unset) falls back to :data:`DEFAULT_CANARY_CAPABILITIES`; an explicitly
    empty/blank value parses to an empty tuple (an operator deliberately narrowing the
    canary to nothing). Whitespace around each label is stripped; empties are dropped."""
    if raw is None:
        return DEFAULT_CANARY_CAPABILITIES
    return tuple(label.strip() for label in raw.split(",") if label.strip())


def canary_capabilities(env: dict[str, str] | None = None) -> frozenset[str]:
    """The EFFECTIVE canary allow-list as normalised capability keys for this env.

    Fail-closed composition of the two guardrails:
      1. **Staging gate** — outside ``BANXE_ENV == staging`` the allow-list is EMPTY, so
         no capability is widened (a leaked flag cannot activate the canary in prod).
      2. **High-risk subtraction** — any configured capability that is high-risk
         (:func:`is_high_risk_capability`) is dropped, so a misconfigured allow-list can
         never admit a money/FX/KYC/etc surface.

    The dispatcher applies the same high-risk denylist again at the boundary; this is
    intentional redundancy (defense-in-depth)."""
    source = env if env is not None else os.environ
    if canary_env(source) != STAGING_ENV_VALUE:
        return frozenset()
    labels = parse_canary_capabilities(source.get(CANARY_CAPABILITIES_ENV))
    keys = {normalize_capability(label) for label in labels}
    return frozenset(key for key in keys if key and not is_high_risk_capability(key))


# ──────────────────────────────────────────────────────────────────────────────────
# Phase 5 canary auto-dispatch POLICY (salvaged additive library, supersedes #190).
#
# Phase 7's ``canary_capabilities`` answers "which capability KEYS may the canary widen
# to in this env". The policy objects below answer the per-decision question "given a
# resolved capability (+ optional matched intent), DISPATCH / withhold-not-canary /
# withhold-high-risk?" — a pure value object built from env and injected into the router.
# They reuse the single ``normalize_capability`` spelling and the same hard denylists
# above, so the two surfaces can never drift apart.
# ──────────────────────────────────────────────────────────────────────────────────


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


def is_high_risk(capability: str, matched_intent: str | None = None) -> bool:
    """True if a capability must never be auto-dispatched in the canary phase.

    Belt-and-suspenders: an explicit normalised-key hit OR any high-risk token found in
    the capability label / matched intent. False-positives are safe (they withhold).
    Mirrors :func:`is_high_risk_capability` but also scans an optional ``matched_intent``
    so a blandly-labelled capability with a high-risk intent is still caught.
    """
    if normalize_capability(capability) in HIGH_RISK_CAPABILITY_KEYS:
        return True
    haystack = f"{capability} {matched_intent or ''}".lower()
    return any(token in haystack for token in HIGH_RISK_TOKENS)


def _parse_allowlist(raw: str) -> frozenset[str]:
    """Parse the comma-separated allowlist into normalised capability keys."""
    return frozenset(normalize_capability(item) for item in raw.split(",") if item.strip())


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
        if normalize_capability(capability) not in self.allowed_capabilities:
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
    "BANXE_ENV_ENV",
    "CANARY_CAPABILITIES_ENV",
    "DEFAULT_CANARY_CAPABILITIES",
    "HIGH_RISK_CAPABILITY_KEYS",
    "HIGH_RISK_TOKENS",
    "STAGING_ENV_VALUE",
    "CanaryDecision",
    "CanaryOutcome",
    "CanaryPolicy",
    "canary_capabilities",
    "canary_env",
    "canary_policy_from_env",
    "is_high_risk",
    "is_high_risk_capability",
    "normalize_capability",
    "parse_canary_capabilities",
]
