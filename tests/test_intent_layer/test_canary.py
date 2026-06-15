"""
tests/test_intent_layer/test_canary.py — FU-2 Phase 7 canary SCOPE + hard guardrails.

Covers ``services/intent_layer/canary.py``: the env-bound, high-risk-subtracted canary
allow-list and the money/FX/wallet/card/KYC/SAR/sanctions denylist. The env is injected
(no os.environ), so every case is deterministic.
"""

from __future__ import annotations

import pytest

from services.intent_layer.canary import (
    CANARY_CAPABILITIES_ENV,
    DEFAULT_CANARY_CAPABILITIES,
    HIGH_RISK_CAPABILITY_KEYS,
    CanaryDecision,
    CanaryPolicy,
    canary_capabilities,
    canary_env,
    canary_policy_from_env,
    is_high_risk,
    is_high_risk_capability,
    normalize_capability,
    parse_canary_capabilities,
)

_STAGING = {"BANXE_ENV": "staging"}


# ── normalize_capability ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("Notifications", "notifications"),
        ("Referral / CRM", "referral"),
        ("Analytics / Reporting (ADR-054)", "analytics"),
        ("Statements (ADR-055)", "statements"),
        ("Card (Wallet/Payments-adjacent)", "card"),
        ("  FX / Exchange  ", "fx"),
    ],
)
def test_normalize_capability(label, key):
    assert normalize_capability(label) == key


# ── high-risk denylist ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label",
    [
        "Payments",
        "FX / Exchange",
        "Wallet",
        "Card (Wallet/Payments-adjacent)",
        "KYC onboarding",
        "Sanctions screening",
        "SAR filing",
        "AML review",
        "Crypto withdrawal",
        "SWIFT transfer",
    ],
)
def test_high_risk_capabilities_are_flagged(label):
    assert is_high_risk_capability(label) is True


@pytest.mark.parametrize(
    "label",
    ["Notifications", "Referral / CRM", "Support", "Statements (ADR-055)"],
)
def test_low_risk_capabilities_are_not_flagged(label):
    assert is_high_risk_capability(label) is False


def test_every_high_risk_key_is_flagged():
    # The exact-key denylist must itself classify as high-risk (no drift).
    assert all(is_high_risk_capability(key) for key in HIGH_RISK_CAPABILITY_KEYS)


# ── parse + env gating ───────────────────────────────────────────────────────────


def test_parse_defaults_to_notifications_when_unset():
    assert parse_canary_capabilities(None) == DEFAULT_CANARY_CAPABILITIES
    assert DEFAULT_CANARY_CAPABILITIES == ("Notifications",)


def test_parse_strips_and_drops_empties():
    assert parse_canary_capabilities(" Notifications , Referral / CRM , ") == (
        "Notifications",
        "Referral / CRM",
    )


def test_parse_blank_is_empty_tuple():
    # An explicit blank narrows the canary to nothing (operator intent), not the default.
    assert parse_canary_capabilities("") == ()
    assert parse_canary_capabilities("   ") == ()


def test_canary_env_reads_banxe_env():
    assert canary_env({"BANXE_ENV": "staging"}) == "staging"
    assert canary_env({"BANXE_ENV": "  Production "}) == "production"
    assert canary_env({}) == "unknown"


# ── effective allow-list ─────────────────────────────────────────────────────────


def test_staging_default_is_notifications_only():
    # No INTENT_LAYER_CANARY_CAPABILITIES set → Phase 6 scope (Notifications only).
    assert canary_capabilities(_STAGING) == frozenset({"notifications"})


def test_staging_widens_to_referral_when_configured():
    env = {**_STAGING, CANARY_CAPABILITIES_ENV: "Notifications,Referral / CRM"}
    assert canary_capabilities(env) == frozenset({"notifications", "referral"})


def test_non_staging_allowlist_is_empty_even_when_configured():
    # Prod-shaped: a permissive allow-list is IGNORED outside staging (dark).
    env = {"BANXE_ENV": "production", CANARY_CAPABILITIES_ENV: "Notifications,Referral / CRM"}
    assert canary_capabilities(env) == frozenset()


def test_unknown_env_allowlist_is_empty():
    assert canary_capabilities({CANARY_CAPABILITIES_ENV: "Notifications"}) == frozenset()


def test_high_risk_is_subtracted_from_allowlist_even_if_misconfigured():
    # Defense-in-depth: an operator that mistakenly lists money-moving surfaces gets
    # them silently dropped — only the low-risk entries survive.
    env = {
        **_STAGING,
        CANARY_CAPABILITIES_ENV: "Notifications,Payments,FX / Exchange,Wallet,KYC onboarding",
    }
    assert canary_capabilities(env) == frozenset({"notifications"})


def test_allowlist_of_only_high_risk_collapses_to_empty():
    env = {**_STAGING, CANARY_CAPABILITIES_ENV: "Payments,FX / Exchange"}
    assert canary_capabilities(env) == frozenset()


# ── Phase 5 canary auto-dispatch POLICY (salvaged from #190) ───────────────────────
# Exercises the additive policy library: is_high_risk (with matched_intent),
# CanaryPolicy.decide and canary_policy_from_env — default-deny allowlist, the hard
# high-risk denylist, and denylist-wins-over-allowlist.


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


def test_high_risk_withheld_even_if_explicitly_allowlisted():
    # Misconfiguration: someone allowlists Payments. The hard denylist still wins.
    policy = CanaryPolicy(allowed_capabilities=frozenset({"payments", "notifications"}))
    outcome = policy.decide("Payments", "pay")
    assert outcome.decision is CanaryDecision.WITHHELD_HIGH_RISK
    assert "high-risk" in outcome.reason


def test_policy_from_env_default_is_deny_all():
    policy = canary_policy_from_env(env={})
    assert policy.allowed_capabilities == frozenset()


def test_policy_from_env_parses_comma_list():
    policy = canary_policy_from_env(env={CANARY_CAPABILITIES_ENV: "Notifications, Statements"})
    assert policy.allowed_capabilities == frozenset({"notifications", "statements"})
