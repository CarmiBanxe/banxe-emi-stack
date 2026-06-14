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

Environment scoping (FU-2 Phase 5 canary):
  Enablement is resolved PER ENVIRONMENT so the layer can be lit in staging without
  touching production. ``APP_ENV`` (or ``ENVIRONMENT``) names the environment; an
  ``INTENT_LAYER_ENABLED_<ENV>`` override, when present, takes precedence over the
  global ``INTENT_LAYER_ENABLED`` for that environment ONLY. A staging override never
  leaks into production:

      APP_ENV=staging  INTENT_LAYER_ENABLED_STAGING=true   → enabled in staging
      APP_ENV=production (no override, global false)        → stays dark

  Note: enablement alone does NOT auto-dispatch anything — the canary allowlist +
  hard-coded high-risk denylist in ``canary.py`` gate which capabilities may actually
  be dispatched. With no allowlist configured, even an enabled layer dispatches
  nothing (default-deny), so a leaked global flag in prod is still mechanically safe.
"""

from __future__ import annotations

import os

INTENT_LAYER_ENABLED_ENV = "INTENT_LAYER_ENABLED"
APP_ENV_KEYS = ("APP_ENV", "ENVIRONMENT")
DEFAULT_ENVIRONMENT = "production"  # fail-safe: an unlabelled env is treated as prod


def _truthy(value: str) -> bool:
    """Conservative parse: only the literal ``true`` (case/space-insensitive) is on."""
    return value.strip().lower() == "true"


def current_environment(env: dict[str, str] | None = None) -> str:
    """Resolve the deployment environment from ``APP_ENV``/``ENVIRONMENT``.

    Defaults to ``production`` when unset — the most restrictive choice, so an
    unlabelled deployment never accidentally inherits a non-prod override.
    """
    source = env if env is not None else os.environ
    for key in APP_ENV_KEYS:
        value = source.get(key)
        if value and value.strip():
            return value.strip().lower()
    return DEFAULT_ENVIRONMENT


def per_env_flag_name(environment: str) -> str:
    """The ``INTENT_LAYER_ENABLED_<ENV>`` override key for an environment."""
    return f"{INTENT_LAYER_ENABLED_ENV}_{environment.upper()}"


def intent_layer_enabled(env: dict[str, str] | None = None) -> bool:
    """Read the effective INTENT_LAYER_ENABLED flag for the current environment.

    Resolution order (injectable env for deterministic tests):
      1. ``INTENT_LAYER_ENABLED_<ENV>`` for the current environment, when present —
         a per-env override scoped to exactly that environment; or
      2. the global ``INTENT_LAYER_ENABLED`` (default false).
    """
    source = env if env is not None else os.environ
    environment = current_environment(source)
    override = source.get(per_env_flag_name(environment))
    if override is not None:
        return _truthy(override)
    return _truthy(source.get(INTENT_LAYER_ENABLED_ENV, "false"))
