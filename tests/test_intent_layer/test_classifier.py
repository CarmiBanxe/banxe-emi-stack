"""
tests/test_intent_layer/test_classifier.py — IntentClassifier: deterministic + LLM + UNRESOLVED
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.models import (
    ConfidenceBand,
    IntentStatus,
    MatchSource,
    ProcessRef,
)
from services.intent_layer.ports import NullLLMClassifier

from .conftest import NINE_CAPABILITIES, StubLLM


@pytest.mark.parametrize(("intent", "capability", "process_id"), NINE_CAPABILITIES)
def test_deterministic_exact_match_all_nine_capabilities(catalog, intent, capability, process_id):
    resolved = IntentClassifier(catalog).classify(intent)
    assert resolved.status is IntentStatus.RESOLVED
    assert resolved.match_source is MatchSource.EXACT
    assert resolved.capability == capability
    assert resolved.process_refs == (ProcessRef(process_id, "1.0.0"),)
    assert resolved.confidence == 1.0
    assert resolved.band is ConfidenceBand.AUTO


def test_alias_match_resolves_same_process(catalog):
    resolved = IntentClassifier(catalog).classify("send money")
    assert resolved.status is IntentStatus.RESOLVED
    assert resolved.match_source is MatchSource.ALIAS
    assert resolved.matched_intent == "pay"
    assert resolved.process_refs == (ProcessRef("payment-processing-process", "1.0.0"),)


def test_unresolved_intent_is_governance_event(catalog):
    resolved = IntentClassifier(catalog).classify("buy me a coffee on the moon")
    assert resolved.status is IntentStatus.UNRESOLVED
    assert resolved.match_source is MatchSource.NONE
    assert resolved.process_refs == ()
    assert resolved.capability is None
    assert resolved.confidence == 0.0
    assert resolved.band is ConfidenceBand.BLOCK


def test_null_llm_default_means_no_fuzzy_match_even_when_enabled(catalog):
    # NullLLMClassifier is the default port → fuzzy abstains → UNRESOLVED, no live LLM.
    classifier = IntentClassifier(catalog, enabled=True)
    assert isinstance(classifier._llm, NullLLMClassifier)
    assert (
        classifier.classify("i would like to move some funds around").status
        is IntentStatus.UNRESOLVED
    )


def test_llm_fallback_consulted_only_when_enabled(catalog):
    stub = StubLLM(text="zap my money over", intent="pay", confidence=0.82)

    disabled = IntentClassifier(catalog, enabled=False, llm=stub)
    assert disabled.classify("zap my money over").status is IntentStatus.UNRESOLVED
    assert stub.calls == []  # gated: not even consulted when disabled

    enabled = IntentClassifier(catalog, enabled=True, llm=stub)
    resolved = enabled.classify("zap my money over")
    assert stub.calls == ["zap my money over"]
    assert resolved.status is IntentStatus.RESOLVED
    assert resolved.match_source is MatchSource.LLM
    assert resolved.matched_intent == "pay"
    assert resolved.confidence == 0.82
    assert resolved.band is ConfidenceBand.REVIEW


def test_llm_proposing_unknown_intent_is_rejected_no_improvisation(catalog):
    # LLM hallucinates a non-catalog token → must NOT resolve to any process_ref.
    stub = StubLLM(text="do the thing", intent="hallucinated-intent", confidence=0.99)
    resolved = IntentClassifier(catalog, enabled=True, llm=stub).classify("do the thing")
    assert resolved.status is IntentStatus.UNRESOLVED


def test_deterministic_wins_before_llm_is_consulted(catalog):
    stub = StubLLM(text="pay", intent="exchange", confidence=0.99)
    resolved = IntentClassifier(catalog, enabled=True, llm=stub).classify("pay")
    assert resolved.match_source is MatchSource.EXACT
    assert resolved.matched_intent == "pay"
    assert stub.calls == []  # deterministic short-circuits the fallback


def test_correlation_id_is_stable_when_supplied_else_generated(catalog):
    classifier = IntentClassifier(catalog)
    assert classifier.classify("pay", correlation_id="corr-123").correlation_id == "corr-123"
    a = classifier.classify("pay").correlation_id
    b = classifier.classify("pay").correlation_id
    assert a and b and a != b  # auto-generated ids are unique per call


def test_confidence_band_boundaries():
    assert ConfidenceBand.of(0.91) is ConfidenceBand.AUTO
    assert ConfidenceBand.of(0.90) is ConfidenceBand.REVIEW
    assert ConfidenceBand.of(0.70) is ConfidenceBand.REVIEW
    assert ConfidenceBand.of(0.69) is ConfidenceBand.BLOCK
