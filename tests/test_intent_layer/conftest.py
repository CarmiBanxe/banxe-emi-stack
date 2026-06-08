"""
tests/test_intent_layer/conftest.py — shared fixtures for the L1 Intent Layer tests
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

All fixtures are in-memory / file-fixture based: the whole layer is exercised with NO
live LLM and NO network, every external dependency injected. INTENT_MAP / REGISTRY
mirror the shape (and the 9 client-facing capabilities) of the real S3 artefacts in
banxe-business-processes/ai-agent-context/.
"""

from __future__ import annotations

import json

import pytest

from services.intent_layer.catalog import IntentCatalog
from services.intent_layer.ports import (
    DispatchReceipt,
    DispatchRequest,
    LLMClassification,
)

# ── The 9 client-facing capabilities (ADR-049 D3), mirroring intent-process-map.yaml ──

INTENT_MAP: dict = {
    "version": "1.0.0",
    "intents": [
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
            "aliases": [
                "sign up",
                "open an account",
                "register",
                "complete KYC",
                "verify identity",
            ],
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
        # adjacent card intents resolving to existing card processes
        {
            "intent": "activate-card",
            "aliases": ["activate my card", "turn on card", "enable card"],
            "capability": "Card",
            "process_ids": ["card-activation"],
        },
        {
            "intent": "order-card",
            "aliases": ["get a card", "new card", "request card", "issue card"],
            "capability": "Card",
            "process_ids": ["card-issuance"],
        },
        {
            "intent": "replace-card",
            "aliases": ["replace card", "lost card replacement", "new card same account"],
            "capability": "Card",
            "process_ids": ["card-replacement"],
        },
    ],
}

REGISTRY: dict = {
    "schema": "ai-agent-context/process_ref.schema.json",
    "processes": [
        {"process_id": "payment-processing-process", "version": "1.0.0"},
        {"process_id": "fx-exchange", "version": "1.0.0"},
        {"process_id": "wallet-balance-inquiry", "version": "1.0.0"},
        {"process_id": "card-blocking", "version": "1.0.0"},
        {"process_id": "onboarding-process", "version": "1.0.0"},
        {"process_id": "statement-generation", "version": "1.0.0"},
        {"process_id": "spending-analytics", "version": "1.0.0"},
        {"process_id": "referral-management", "version": "1.0.0"},
        {"process_id": "notification-dispatch", "version": "1.0.0"},
        {"process_id": "card-activation", "version": "1.0.0"},
        {"process_id": "card-issuance", "version": "1.0.0"},
        {"process_id": "card-replacement", "version": "1.0.0"},
    ],
}

# Expected (intent, capability, process_id) for the 9 primary client-facing capabilities.
NINE_CAPABILITIES = [
    ("pay", "Payments", "payment-processing-process"),
    ("exchange", "FX / Exchange", "fx-exchange"),
    ("view-balance", "Wallet", "wallet-balance-inquiry"),
    ("freeze-card", "Card (Wallet/Payments-adjacent)", "card-blocking"),
    ("onboard-kyc", "KYC onboarding", "onboarding-process"),
    ("get-statement", "Statements (ADR-055)", "statement-generation"),
    ("see-spending", "Analytics / Reporting (ADR-054)", "spending-analytics"),
    ("refer-a-friend", "Referral / CRM", "referral-management"),
    ("get-notified", "Notifications", "notification-dispatch"),
]


@pytest.fixture()
def catalog() -> IntentCatalog:
    return IntentCatalog.from_data(INTENT_MAP, REGISTRY)


class SpyDispatcher:
    """AgentDispatchPort double — records every dispatch and returns a canned receipt."""

    def __init__(self, *, accepted: bool = True) -> None:
        self.calls: list[DispatchRequest] = []
        self._accepted = accepted

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt:
        self.calls.append(request)
        return DispatchReceipt(accepted=self._accepted, agent=f"agent:{request.capability}")


@pytest.fixture()
def spy_dispatcher() -> SpyDispatcher:
    return SpyDispatcher()


class StubLLM:
    """LLMClassifierPort double — maps a fixed text to a fixed intent token."""

    def __init__(self, *, text: str, intent: str, confidence: float) -> None:
        self._text = text
        self._intent = intent
        self._confidence = confidence
        self.calls: list[str] = []

    def classify(self, intent_text: str, candidates: list) -> LLMClassification | None:
        self.calls.append(intent_text)
        if intent_text == self._text:
            return LLMClassification(matched_intent=self._intent, confidence=self._confidence)
        return None


@pytest.fixture()
def map_files(tmp_path) -> tuple[str, str]:
    """Write the S3 artefacts to disk for the from_files() path (needs PyYAML)."""
    import yaml

    map_path = tmp_path / "intent-process-map.yaml"
    reg_path = tmp_path / "processes-registry.json"
    map_path.write_text(yaml.safe_dump(INTENT_MAP), encoding="utf-8")
    reg_path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    return str(map_path), str(reg_path)
