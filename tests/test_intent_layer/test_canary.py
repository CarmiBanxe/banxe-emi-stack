"""
tests/test_intent_layer/test_canary.py — FU-2 Phase 5 canary policy + denylist
banxe-emi-stack

Proves the mechanistic guardrails of the staging canary:
  • default-deny allowlist (empty → nothing dispatches),
  • the hard-coded high-risk denylist (payments/FX/wallet/card/KYC/SAR/sanctions),
  • denylist wins over the allowlist (a mislabelled high-risk capability is still
    withheld even if explicitly allowlisted),
  • normalisation matches the dispatcher's capability keying.
"""

from __future__ import annotations

import pytest

from services.intent_layer.canary import (
    CANARY_CAPABILITIES_ENV,
    CanaryDecision,
    CanaryPolicy,
    canary_policy_from_env,
    is_high_risk,
    normalise_capability,
)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Notifications", "notifications"),
        ("FX / Exchange", "fx"),
        ("Analytics / Reporting (ADR-054)", "analytics"),
        ("  Statements (ADR-055) ", "statements"),
    ],
)
def test_normalise_capability(label, expected):
    assert normalise_capability(label) == expected


# ── High-risk denylist ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "capability",
    [
        "Payments",
        "FX / Exchange",
        "Wallet",
        "Card (Wallet/Payments-adjacent)",
        "KYC onboarding",
        # New / mislabelled high-risk capabilities caught by the token scan:
        "Cross-border payment",
        "Wire transfer",
        "Sanctions screening",
        "SAR filing",
    ],
)
def test_high_risk_capabilities_are_denied(capability):
    assert is_high_risk(capability) is True


@pytest.mark.parametrize(
    "capability",
    ["Notifications", "Statements (ADR-055)", "Analytics / Reporting (ADR-054)", "Referral / CRM"],
)
def test_low_risk_capabilities_are_not_denied(capability):
    assert is_high_risk(capability) is False


def test_high_risk_detected_via_matched_intent_token():
    # A blandly-labelled capability whose intent token is high-risk is still caught.
    assert is_high_risk("Support", matched_intent="onboard-kyc") is True


# ── Allowlist (default-deny) ──────────────────────────────────────────────────────


def test_empty_allowlist_withholds_low_risk_capability():
    policy = CanaryPolicy(allowed_capabilities=frozenset())
    outcome = policy.decide("Notifications", "get-notified")
    assert outcome.decision is CanaryDecision.WITHHELD_NOT_CANARY


def test_allowlisted_low_risk_capability_dispatches():
    policy = CanaryPolicy(allowed_capabilities=frozenset({"notifications"}))
    outcome = policy.decide("Notifications", "get-notified")
    assert outcome.decision is CanaryDecision.DISPATCH


def test_non_allowlisted_low_risk_capability_withheld():
    policy = CanaryPolicy(allowed_capabilities=frozenset({"notifications"}))
    outcome = policy.decide("Statements (ADR-055)", "get-statement")
    assert outcome.decision is CanaryDecision.WITHHELD_NOT_CANARY


# ── Denylist beats the allowlist (mechanistic guardrail) ──────────────────────────


def test_high_risk_withheld_even_if_explicitly_allowlisted():
    # Misconfiguration: someone allowlists Payments. The hard denylist still wins.
    policy = CanaryPolicy(allowed_capabilities=frozenset({"payments", "notifications"}))
    outcome = policy.decide("Payments", "pay")
    assert outcome.decision is CanaryDecision.WITHHELD_HIGH_RISK
    assert "high-risk" in outcome.reason


# ── Env builder ───────────────────────────────────────────────────────────────────


def test_policy_from_env_default_is_deny_all():
    policy = canary_policy_from_env(env={})
    assert policy.allowed_capabilities == frozenset()


def test_policy_from_env_parses_comma_list():
    policy = canary_policy_from_env(env={CANARY_CAPABILITIES_ENV: "Notifications, Statements"})
    assert policy.allowed_capabilities == frozenset({"notifications", "statements"})
