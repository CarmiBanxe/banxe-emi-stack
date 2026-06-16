"""
services/intent_layer/catalog_snapshot.py — self-contained intent catalogue loader.

The canonical intent→process map + registry live in banxe-business-processes
(``ai-agent-context/intent-process-map.yaml`` + ``processes-registry.json``). The
HTTP entrypoint must build a catalogue without a hard dependency on that sibling
repo being present, so this loader:

  1. prefers the live S3 files when their paths are supplied via
     ``INTENT_PROCESS_MAP_PATH`` + ``INTENT_PROCESS_REGISTRY_PATH`` (operator
     wiring — always the source of truth when available); else
  2. falls back to an EMBEDDED SNAPSHOT of the canonical rows, so the endpoint is
     self-contained in CI / dev.

The snapshot mirrors the canonical capabilities + process_ids; every process
version is ``1.0.0`` exactly as in the committed registry. It is a convenience
mirror, NOT a second source of truth — the operator path (1) overrides it.
"""

from __future__ import annotations

import os

from services.intent_layer.catalog import IntentCatalog

MAP_PATH_ENV = "INTENT_PROCESS_MAP_PATH"
REGISTRY_PATH_ENV = "INTENT_PROCESS_REGISTRY_PATH"

# Embedded snapshot of the canonical intent→process map (the 9 client-facing
# capabilities + adjacent card intents). process_ids resolve against the snapshot
# registry below; versions match the committed processes-registry.json (all 1.0.0).
_SNAPSHOT_INTENTS = [
    {
        "intent": "pay",
        "aliases": ["transfer", "send money", "make a payment", "move funds"],
        "capability": "Payments",
        "process_ids": ["payment-processing-process"],
    },
    {
        "intent": "exchange",
        "aliases": ["fx", "convert currency", "currency exchange", "swap currency"],
        "capability": "FX / Exchange",
        "process_ids": ["fx-exchange"],
    },
    {
        "intent": "view-balance",
        "aliases": ["check balance", "view balance", "what's my balance", "manage wallet"],
        "capability": "Wallet",
        "process_ids": ["wallet-balance-inquiry"],
    },
    {
        "intent": "freeze-card",
        "aliases": ["block card", "freeze my card", "lock card", "report card lost/stolen"],
        "capability": "Card (Wallet/Payments-adjacent)",
        "process_ids": ["card-blocking"],
    },
    {
        "intent": "onboard-kyc",
        "aliases": ["sign up", "open an account", "register", "complete KYC", "verify identity"],
        "capability": "KYC onboarding",
        "process_ids": ["onboarding-process"],
    },
    {
        "intent": "get-statement",
        "aliases": ["statement", "download statement", "account statement", "get my statement"],
        "capability": "Statements (ADR-055)",
        "process_ids": ["statement-generation"],
    },
    {
        "intent": "see-spending",
        "aliases": ["spending", "spending breakdown", "where did my money go", "insights"],
        "capability": "Analytics / Reporting (ADR-054)",
        "process_ids": ["spending-analytics"],
    },
    {
        "intent": "refer-a-friend",
        "aliases": ["referral", "invite a friend", "refer", "share invite"],
        "capability": "Referral / CRM",
        "process_ids": ["referral-management"],
    },
    {
        "intent": "get-notified",
        "aliases": ["notifications", "alerts", "notify me", "manage notifications"],
        "capability": "Notifications",
        "process_ids": ["notification-dispatch"],
    },
]

_SNAPSHOT_PROCESS_IDS = [
    "payment-processing-process",
    "fx-exchange",
    "wallet-balance-inquiry",
    "card-blocking",
    "onboarding-process",
    "statement-generation",
    "spending-analytics",
    "referral-management",
    "notification-dispatch",
]


def _snapshot_catalog() -> IntentCatalog:
    intent_map = {"intents": _SNAPSHOT_INTENTS}
    registry = {
        "processes": [{"process_id": pid, "version": "1.0.0"} for pid in _SNAPSHOT_PROCESS_IDS]
    }
    return IntentCatalog.from_data(intent_map, registry)


def load_catalog(env: dict[str, str] | None = None) -> IntentCatalog:
    """Load the catalogue: live S3 files when their paths are set, else the snapshot."""
    source = env if env is not None else os.environ
    map_path = source.get(MAP_PATH_ENV)
    registry_path = source.get(REGISTRY_PATH_ENV)
    if map_path and registry_path:
        return IntentCatalog.from_files(map_path, registry_path)
    return _snapshot_catalog()


__all__ = ["MAP_PATH_ENV", "REGISTRY_PATH_ENV", "load_catalog"]
