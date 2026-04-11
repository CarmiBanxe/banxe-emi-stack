"""
tests/test_agent_routing/test_reasoning_bank.py — ReasoningBank tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: store/retrieve, similarity search, reuse qualification, feedback (I-27).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from services.reasoning_bank.models import (
    CaseRecord,
    DecisionRecord,
    FeedbackRecord,
    PolicySnapshot,
    ReasoningRecord,
)
from services.reasoning_bank.store import ReasoningBankStore

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_case(case_id: str | None = None) -> CaseRecord:
    return CaseRecord(
        case_id=case_id or str(uuid.uuid4()),
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_001",
        risk_context={"amount_eur": 500},
        playbook_id="eu_sepa_retail_v1",
        tier_used=1,
        created_at=datetime.now(UTC),
    )


def make_decision(case_id: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=str(uuid.uuid4()),
        case_id=case_id,
        decision="approve",
        final_risk_score=0.1,
        decided_by="tier1_rule_engine",
        decided_at=datetime.now(UTC),
    )


def make_reasoning(case_id: str) -> ReasoningRecord:
    return ReasoningRecord(
        reasoning_id=str(uuid.uuid4()),
        case_id=case_id,
        internal_view="Internal: rule-based clear pass",
        audit_view="Audit: no red flags found per MLR 2017",
        customer_view="Your transaction was approved",
        token_cost=0,
        model_used="rule_engine_v1",
        created_at=datetime.now(UTC),
    )


def make_policy(case_id: str) -> PolicySnapshot:
    return PolicySnapshot(
        snapshot_id=str(uuid.uuid4()),
        case_id=case_id,
        playbook_id="eu_sepa_retail_v1",
        playbook_version="1.0",
        policy_hash="abc123",
        captured_at=datetime.now(UTC),
    )


def make_vector(dim: int = 4) -> list[float]:
    return [0.5] * dim


@pytest.fixture
def store() -> ReasoningBankStore:
    return ReasoningBankStore(embedding_dim=4)


# ── Store / Retrieve ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_case_returns_case_id(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    reasoning = make_reasoning(case.case_id)
    result = await store.store_case(case, decision, reasoning)
    assert result == case.case_id


@pytest.mark.asyncio
async def test_get_case_after_store(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    reasoning = make_reasoning(case.case_id)
    await store.store_case(case, decision, reasoning)
    retrieved = await store.get_case(case.case_id)
    assert retrieved is not None
    assert retrieved.case_id == case.case_id
    assert retrieved.event_type == "aml_screening"


@pytest.mark.asyncio
async def test_get_case_unknown_returns_none(store: ReasoningBankStore) -> None:
    result = await store.get_case("nonexistent_case")
    assert result is None


@pytest.mark.asyncio
async def test_get_decision_after_store(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    reasoning = make_reasoning(case.case_id)
    await store.store_case(case, decision, reasoning)
    retrieved = await store.get_decision(case.case_id)
    assert retrieved is not None
    assert retrieved.decision == "approve"


@pytest.mark.asyncio
async def test_get_reusable_reasoning(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    reasoning = make_reasoning(case.case_id)
    await store.store_case(case, decision, reasoning)
    result = await store.get_reusable_reasoning(case.case_id)
    assert result is not None
    assert result.internal_view == "Internal: rule-based clear pass"
    assert result.audit_view == "Audit: no red flags found per MLR 2017"
    assert result.customer_view == "Your transaction was approved"


@pytest.mark.asyncio
async def test_overridden_reasoning_not_reusable(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    decision.overridden = True
    decision.override_reason = "MLRO reversed decision"
    reasoning = make_reasoning(case.case_id)
    await store.store_case(case, decision, reasoning)
    result = await store.get_reusable_reasoning(case.case_id)
    assert result is None


# ── Similarity search ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_similar_empty_store(store: ReasoningBankStore) -> None:
    result = await store.find_similar([0.5, 0.5, 0.5, 0.5])
    assert result == []


@pytest.mark.asyncio
async def test_find_similar_returns_matching_case(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    reasoning = make_reasoning(case.case_id)
    vec = [1.0, 0.0, 0.0, 0.0]
    await store.store_case(case, decision, reasoning, embedding=vec)
    results = await store.find_similar([1.0, 0.0, 0.0, 0.0], threshold=0.99)
    assert len(results) >= 1
    assert results[0].case_id == case.case_id


@pytest.mark.asyncio
async def test_find_similar_below_threshold_excluded(store: ReasoningBankStore) -> None:
    case = make_case()
    decision = make_decision(case.case_id)
    reasoning = make_reasoning(case.case_id)
    await store.store_case(case, decision, reasoning, embedding=[1.0, 0.0, 0.0, 0.0])
    # Orthogonal vector — cosine similarity = 0
    results = await store.find_similar([0.0, 1.0, 0.0, 0.0], threshold=0.85)
    assert results == []


@pytest.mark.asyncio
async def test_find_similar_top_k_respected(store: ReasoningBankStore) -> None:
    for i in range(5):
        case = make_case()
        decision = make_decision(case.case_id)
        reasoning = make_reasoning(case.case_id)
        # All same direction — all will match
        await store.store_case(case, decision, reasoning, embedding=[1.0, 0.0, 0.0, 0.0])
    results = await store.find_similar([1.0, 0.0, 0.0, 0.0], top_k=3, threshold=0.9)
    assert len(results) <= 3


# ── Feedback (I-27) ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_feedback(store: ReasoningBankStore) -> None:
    feedback = FeedbackRecord(
        feedback_id=str(uuid.uuid4()),
        case_id="case_001",
        feedback_type="false_positive",
        provided_by="MLRO",
        note="Transaction was flagged incorrectly",
        recorded_at=datetime.now(UTC),
    )
    await store.record_feedback(feedback)
    results = await store.get_feedback("case_001")
    assert len(results) == 1
    assert results[0].feedback_type == "false_positive"


@pytest.mark.asyncio
async def test_feedback_not_auto_applied(store: ReasoningBankStore) -> None:
    feedback = FeedbackRecord(
        feedback_id=str(uuid.uuid4()),
        case_id="case_002",
        feedback_type="sar_filed",
        provided_by="MLRO",
        note="SAR submitted to NCA",
        recorded_at=datetime.now(UTC),
    )
    await store.record_feedback(feedback)
    results = await store.get_feedback("case_002")
    assert results[0].applied_to_model is False  # I-27


@pytest.mark.asyncio
async def test_get_feedback_unknown_case_empty(store: ReasoningBankStore) -> None:
    results = await store.get_feedback("nonexistent")
    assert results == []


# ── Stats ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_empty_store(store: ReasoningBankStore) -> None:
    stats = store.stats()
    assert stats["cases"] == 0
    assert stats["decisions"] == 0
    assert stats["reasoning"] == 0


@pytest.mark.asyncio
async def test_stats_after_store(store: ReasoningBankStore) -> None:
    case = make_case()
    await store.store_case(make_case(), make_decision(case.case_id), make_reasoning(case.case_id))
    stats = store.stats()
    assert stats["cases"] >= 1


# ── Policy hash ────────────────────────────────────────────────────────────────


def test_policy_hash_is_deterministic(store: ReasoningBankStore) -> None:
    h1 = store.compute_policy_hash("playbook content")
    h2 = store.compute_policy_hash("playbook content")
    assert h1 == h2


def test_policy_hash_different_content(store: ReasoningBankStore) -> None:
    h1 = store.compute_policy_hash("version 1")
    h2 = store.compute_policy_hash("version 2")
    assert h1 != h2


def test_normalise_zero_vector(store: ReasoningBankStore) -> None:
    result = store._normalise([0.0, 0.0, 0.0])
    assert result == [0.0, 0.0, 0.0]
