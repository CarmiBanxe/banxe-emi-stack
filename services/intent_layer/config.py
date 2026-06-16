"""
services/intent_layer/config.py — L1 Intent Layer feature flag
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

INTENT_LAYER_ENABLED governs the ADR-049 client L1 Intent Layer. It is DISTINCT from
ADR-021's AGENT_ROUTING_ENABLED (the internal compliance/AML/KYC tier-worker router) —
the two layers are separate concerns and MUST NOT share a flag. Default false: the
layer is inert until explicitly activated, so it is safe to ship pre-activation.

Gating semantics:
  - false → IntentRouter.route() returns NOT_ENABLED (no dispatch); the LLM fuzzy
            fallback in IntentClassifier is also suppressed.
  - true  → deterministic classification dispatches; LLM fallback is consulted when a
            non-Null LLMClassifierPort is injected (S1 gateway).
"""

from __future__ import annotations

import os

INTENT_LAYER_ENABLED_ENV = "INTENT_LAYER_ENABLED"


def intent_layer_enabled(env: dict[str, str] | None = None) -> bool:
    """Read the INTENT_LAYER_ENABLED flag. Injectable env for deterministic tests."""
    source = env if env is not None else os.environ
    return source.get(INTENT_LAYER_ENABLED_ENV, "false").strip().lower() == "true"
