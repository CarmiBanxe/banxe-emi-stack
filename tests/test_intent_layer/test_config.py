"""
tests/test_intent_layer/test_config.py — INTENT_LAYER_ENABLED flag (distinct from ADR-021)
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.intent_layer.config import (
    INTENT_LAYER_ENABLED_ENV,
    intent_layer_enabled,
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
