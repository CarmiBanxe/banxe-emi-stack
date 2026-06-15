"""
tests/test_intent_layer/test_intent_layer_dark_mode.py — FU-2 Phase 3 DARK-MODE proof.

Exercises the ADR-049 L1 Intent Layer end-to-end with ``INTENT_LAYER_ENABLED=false``
(the default in every environment) and proves it is genuinely INERT:

  * every typical client intent (payments, FX, wallet, notifications, KYC, …) routes
    to ``NOT_ENABLED`` — never DISPATCHED, never a governance event;
  * NO external side effect fires: the injected ``AgentDispatchPort`` is an exploding
    double that fails the test if ``dispatch()`` is ever called — proving no outbound
    HTTP, no payment-core adapter, no L2 mask invocation;
  * the LLM fuzzy fallback is suppressed — an exploding ``LLMClassifierPort`` is never
    consulted while disabled;
  * NO lineage record is emitted — neither to the in-memory sink nor (even when
    ``DECISION_RECORDER=clickhouse`` is selected) to the durable ClickHouse sink, which
    is wired with an exploding client that fails on any insert/query.

The HTTP entrypoint (POST /v1/intent) is also driven through FastAPI's TestClient for
the same intents, asserting the dark ``NOT_ENABLED`` envelope and that nothing is
retrievable by ``correlation_id`` afterwards.

This phase does NOT activate the Intent Layer for real traffic — it only verifies the
safe pre-activation contract. The live ClickHouse round-trip stays opt-in behind
``DECISION_RECORDER_TEST_DSN`` so CI is green without ClickHouse.
"""

from __future__ import annotations

import os

import pytest

from services.agents.recorders import ClickHouseDecisionRecorder
from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.composition import (
    CapabilityDispatcher,
    InMemoryDecisionRecorder,
)
from services.intent_layer.config import (
    INTENT_LAYER_ENABLED_ENV,
    intent_layer_enabled,
)
from services.intent_layer.models import DispositionKind
from services.intent_layer.ports import (
    DispatchReceipt,
    DispatchRequest,
    IntentDefinition,
    LLMClassification,
)
from services.intent_layer.router import IntentRouter
from services.producers.bundle import ProducerBundle

# Typical client intents across the 9 capabilities (mix of canonical tokens + aliases).
DARK_INTENTS = [
    "pay",
    "send money",
    "exchange",
    "convert currency",
    "view-balance",
    "freeze-card",
    "onboard-kyc",
    "get-statement",
    "notifications",
    "alerts",
]


# ── Exploding doubles: any side effect in dark mode is a test failure ────────────


class ExplodingDispatcher:
    """``AgentDispatchPort`` that MUST NOT be called while disabled. Any dispatch is a
    forbidden external side effect (an L2 mask / payment-core adapter / outbound call),
    so it fails the test loudly instead of silently performing it."""

    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt:
        self.calls += 1
        raise AssertionError(
            "AgentDispatchPort.dispatch() called while INTENT_LAYER_ENABLED=false "
            "— forbidden side effect in dark mode"
        )


class ExplodingLLM:
    """``LLMClassifierPort`` that MUST NOT be consulted while disabled — the fuzzy LLM
    fallback is suppressed in dark mode (config.py gating semantics)."""

    def __init__(self) -> None:
        self.calls = 0

    def classify(
        self, intent_text: str, candidates: list[IntentDefinition]
    ) -> LLMClassification | None:
        self.calls += 1
        raise AssertionError(
            "LLM fuzzy fallback consulted while INTENT_LAYER_ENABLED=false — forbidden"
        )


class ExplodingClickHouseClient:
    """``ClickHouseClient`` that fails on any insert/query — proves the durable lineage
    sink is never touched while dark, even when ``DECISION_RECORDER=clickhouse``."""

    def insert(self, query: str, row: dict[str, object]) -> None:
        raise AssertionError("ClickHouse insert while INTENT_LAYER_ENABLED=false — forbidden")

    def query(self, query: str, params: dict[str, object] | None = None) -> list[tuple]:
        raise AssertionError("ClickHouse query while INTENT_LAYER_ENABLED=false — forbidden")


def _exploding_handler(request: DispatchRequest, outputs, recorder) -> None:
    raise AssertionError("L2 mask invoked while INTENT_LAYER_ENABLED=false — forbidden")


# ── Pure-layer dark mode: classify → route, every intent inert ───────────────────


@pytest.mark.parametrize("text", DARK_INTENTS)
def test_dark_mode_intent_is_inert_no_dispatch(catalog, text):
    """Each typical intent → NOT_ENABLED, no dispatch, LLM fallback never consulted."""
    dispatcher = ExplodingDispatcher()
    llm = ExplodingLLM()
    classifier = IntentClassifier(catalog, enabled=False, llm=llm)
    router = IntentRouter(dispatcher, enabled=False)

    resolved = classifier.classify(text, correlation_id=f"dark-{text}")
    disposition = router.route(resolved)

    assert disposition.kind is DispositionKind.NOT_ENABLED
    assert disposition.receipt is None
    assert dispatcher.calls == 0  # no L2 mask / adapter / outbound call
    assert llm.calls == 0  # fuzzy fallback suppressed while dark


def test_dark_mode_unresolved_short_circuits_to_not_enabled(catalog):
    """The flag gate precedes the governance-event branch: even an UNRESOLVED intent
    yields NOT_ENABLED while dark (no governance event, no dispatch)."""
    dispatcher = ExplodingDispatcher()
    classifier = IntentClassifier(catalog, enabled=False, llm=ExplodingLLM())
    router = IntentRouter(dispatcher, enabled=False)

    resolved = classifier.classify("zxqw gibberish nonsense", correlation_id="dark-unres")
    disposition = router.route(resolved)

    assert disposition.kind is DispositionKind.NOT_ENABLED
    assert dispatcher.calls == 0


# ── Lineage: nothing recorded while dark (in-memory + ClickHouse sinks) ───────────


def test_dark_mode_emits_no_inmemory_lineage_record(catalog):
    """With a real CapabilityDispatcher wired to an in-memory sink, a disabled router
    never dispatches, so no AgentDecisionRecord is ever emitted."""
    recorder = InMemoryDecisionRecorder()
    dispatcher = CapabilityDispatcher(
        handlers={"Notifications": _exploding_handler},
        producers=ProducerBundle.null(),
        recorder=recorder,
    )
    router = IntentRouter(dispatcher, enabled=False)
    classifier = IntentClassifier(catalog, enabled=False)

    disposition = router.route(classifier.classify("notifications", correlation_id="dark-notif"))

    assert disposition.kind is DispositionKind.NOT_ENABLED
    assert recorder.records == []
    assert recorder.get_by_correlation("dark-notif") is None


def test_dark_mode_clickhouse_sink_is_never_touched(catalog, monkeypatch):
    """Even with DECISION_RECORDER=clickhouse selected, dark mode records NOTHING: the
    durable sink's client raises on any insert/query and is proven never reached."""
    monkeypatch.setenv("DECISION_RECORDER", "clickhouse")
    recorder = ClickHouseDecisionRecorder(client=ExplodingClickHouseClient())
    dispatcher = CapabilityDispatcher(
        handlers={"Notifications": _exploding_handler},
        producers=ProducerBundle.null(),
        recorder=recorder,
    )
    router = IntentRouter(dispatcher, enabled=False)
    classifier = IntentClassifier(catalog, enabled=False)

    disposition = router.route(classifier.classify("alerts", correlation_id="dark-ch"))

    # ExplodingClickHouseClient would have raised if insert/query were ever called.
    assert disposition.kind is DispositionKind.NOT_ENABLED


# ── Flag default: dark in every environment ──────────────────────────────────────


def test_flag_defaults_to_dark_when_unset(monkeypatch):
    """INTENT_LAYER_ENABLED is false by default (the guardrail for every env)."""
    monkeypatch.delenv(INTENT_LAYER_ENABLED_ENV, raising=False)
    assert intent_layer_enabled() is False


@pytest.mark.parametrize("value", ["false", "False", "  FALSE  ", "0", "no", ""])
def test_flag_non_true_values_stay_dark(value):
    """Only an explicit, case-insensitive 'true' enables the layer; everything else is dark."""
    assert intent_layer_enabled(env={INTENT_LAYER_ENABLED_ENV: value}) is False


# ── HTTP entrypoint dark mode (POST /v1/intent through TestClient) ───────────────


@pytest.mark.parametrize(
    "intent_text", ["pay", "exchange", "view-balance", "onboard-kyc", "notifications"]
)
def test_http_dark_mode_not_enabled_no_record(intent_text, monkeypatch):
    """The HTTP surface returns the inert NOT_ENABLED envelope and persists no record."""
    monkeypatch.setenv(INTENT_LAYER_ENABLED_ENV, "false")
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    cid = f"http-dark-{intent_text}"
    resp = client.post("/v1/intent", json={"intent_text": intent_text, "correlation_id": cid})

    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["disposition"] == "NOT_ENABLED"
    assert body["decision_record"] is None
    assert body["governance_event"] is None
    # Nothing was recorded → the lineage GET is a 404.
    assert client.get(f"/v1/intent/decision/{cid}").status_code == 404


# ── Live ClickHouse dark-mode check (opt-in) ─────────────────────────────────────

_LIVE_DSN = os.environ.get("DECISION_RECORDER_TEST_DSN")


@pytest.mark.skipif(
    not _LIVE_DSN,
    reason="Set DECISION_RECORDER_TEST_DSN to run the live ClickHouse dark-mode check",
)
def test_dark_mode_live_clickhouse_records_nothing(catalog):  # pragma: no cover - opt-in only
    """Wired to a LIVE ClickHouse sink, a disabled router still writes nothing: a fresh
    correlation id has no rows after routing a dark intent."""
    from services.agents.recorders import _DriverClickHouseClient

    recorder = ClickHouseDecisionRecorder(client=_DriverClickHouseClient())
    dispatcher = CapabilityDispatcher(
        handlers={"Notifications": _exploding_handler},
        producers=ProducerBundle.null(),
        recorder=recorder,
    )
    router = IntentRouter(dispatcher, enabled=False)
    classifier = IntentClassifier(catalog, enabled=False)

    cid = "dark-live-" + os.urandom(8).hex()
    disposition = router.route(classifier.classify("notifications", correlation_id=cid))

    assert disposition.kind is DispositionKind.NOT_ENABLED
    assert recorder.query(correlation_id=cid) == []
