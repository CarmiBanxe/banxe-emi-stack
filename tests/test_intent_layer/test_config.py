"""
tests/test_intent_layer/test_config.py — INTENT_LAYER_ENABLED flag (distinct from ADR-021)
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.intent_layer.config import (
    INTENT_LAYER_ENABLED_ENV,
    current_environment,
    intent_layer_enabled,
    per_env_flag_name,
)


def test_flag_name_is_distinct_from_adr021():
    # MUST NOT collide with ADR-021's AGENT_ROUTING_ENABLED.
    assert INTENT_LAYER_ENABLED_ENV == "INTENT_LAYER_ENABLED"
    assert INTENT_LAYER_ENABLED_ENV != "AGENT_ROUTING_ENABLED"


def test_default_is_false_when_unset():
    assert intent_layer_enabled(env={}) is False


@pytest.mark.parametrize("value", ["true", "TRUE", "  True  ", "tRuE"])
def test_truthy_values(value):
    assert intent_layer_enabled(env={INTENT_LAYER_ENABLED_ENV: value}) is True


@pytest.mark.parametrize("value", ["false", "0", "no", "", "yes", "1"])
def test_only_literal_true_enables(value):
    # Conservative: anything that is not "true" leaves the layer inert.
    assert intent_layer_enabled(env={INTENT_LAYER_ENABLED_ENV: value}) is False


def test_reads_process_environ_by_default(monkeypatch):
    monkeypatch.setenv(INTENT_LAYER_ENABLED_ENV, "true")
    assert intent_layer_enabled() is True
    monkeypatch.delenv(INTENT_LAYER_ENABLED_ENV, raising=False)
    assert intent_layer_enabled() is False


# ── FU-2 Phase 5: per-environment scoping ────────────────────────────────────────


def test_environment_defaults_to_production_when_unset():
    assert current_environment(env={}) == "production"


@pytest.mark.parametrize("key", ["APP_ENV", "ENVIRONMENT"])
def test_environment_read_from_either_key(key):
    assert current_environment(env={key: "Staging"}) == "staging"


def test_per_env_flag_name():
    assert per_env_flag_name("staging") == "INTENT_LAYER_ENABLED_STAGING"


def test_staging_override_enables_only_in_staging():
    env = {"APP_ENV": "staging", "INTENT_LAYER_ENABLED_STAGING": "true"}
    assert intent_layer_enabled(env=env) is True


def test_staging_override_does_not_leak_into_production():
    # A staging override MUST NOT enable the layer in production (no global flag set).
    env = {"APP_ENV": "production", "INTENT_LAYER_ENABLED_STAGING": "true"}
    assert intent_layer_enabled(env=env) is False


def test_per_env_override_takes_precedence_over_global():
    # Even with the global flag true, a per-env "false" override keeps that env dark.
    env = {
        "APP_ENV": "staging",
        INTENT_LAYER_ENABLED_ENV: "true",
        "INTENT_LAYER_ENABLED_STAGING": "false",
    }
    assert intent_layer_enabled(env=env) is False


def test_global_flag_still_applies_when_no_override():
    env = {"APP_ENV": "staging", INTENT_LAYER_ENABLED_ENV: "true"}
    assert intent_layer_enabled(env=env) is True
