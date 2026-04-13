"""
tests/test_reasoning_bank.py — ReasoningBank store + API router tests
S14-03 | banxe-emi-stack

Tests for:
  services/reasoning_bank/store.py (79% → ≥95%)
  services/reasoning_bank/api.py (0% → ≥90%)

ReasoningBank provides structured compliance decision storage with
3 reasoning views (GDPR Art.22: internal, audit, customer).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from services.reasoning_bank.api import get_store, router
from services.reasoning_bank.models import (
    CaseRecord,
    DecisionRecord,
    FeedbackRecord,
    PolicySnapshot,
    ReasoningRecord,
)
from services.reasoning_bank.store import ReasoningBankStore

# ── Standalone test app ────────────────────────────────────────────────────────

_app = FastAPI()
_app.include_router(router)

client = TestClient(_app)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


def _store_payload(case_id: str = "case-001") -> dict:
    return {
        "case_id": case_id,
        "event_type": "aml_screening",
        "product": "emoney_account",
        "jurisdiction": "UK",
        "customer_id": "cust-001",
        "risk_context": {"velocity_score": 0.6, "sanctions_hit": False},
        "playbook_id": "pb-aml-v2",
        "tier_used": 2,
        "decision": "approve",
        "final_risk_score": 0.42,
        "decided_by": "claude-tier2",
        "internal_reasoning": "Velocity score 0.6 below AML threshold 0.7. No sanctions hit.",
        "audit_reasoning": "Automated AML screening: low risk.",
        "customer_reasoning": "Payment processed successfully.",
        "token_cost": 1200,
        "model_used": "claude-sonnet-4-6",
    }


@pytest.fixture()
def store() -> ReasoningBankStore:
    return ReasoningBankStore()


@pytest.fixture(autouse=True)
def fresh_store():
    """Override the singleton store for every test."""
    fresh = ReasoningBankStore()
    _app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    _app.dependency_overrides.pop(get_store, None)


# ── Store: store_case ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_case_persists_case_record(store: ReasoningBankStore) -> None:
    case = CaseRecord(
        case_id="c-001",
        event_type="aml_screening",
        product="emoney",
        jurisdiction="UK",
        customer_id="cust-001",
        risk_context={},
        playbook_id="pb-v1",
        tier_used=1,
        created_at=_now(),
    )
    decision = DecisionRecord(
        decision_id="d-001",
        case_id="c-001",
        decision="approve",
        final_risk_score=0.3,
        decided_by="tier1",
        decided_at=_now(),
    )
    reasoning = ReasoningRecord(
        reasoning_id="r-001",
        case_id="c-001",
        internal_view="internal",
        audit_view="audit",
        customer_view="customer",
        token_cost=100,
        model_used="claude-sonnet-4-6",
        created_at=_now(),
    )
    result = await store.store_case(case=case, decision=decision, reasoning=reasoning)
    assert result == "c-001"
    assert "c-001" in store._cases


@pytest.mark.asyncio
async def test_store_case_with_embedding(store: ReasoningBankStore) -> None:
    case = CaseRecord(
        case_id="c-emb-001",
        event_type="fraud",
        product="fx",
        jurisdiction="UK",
        customer_id="cust-emb",
        risk_context={},
        playbook_id="pb-fraud",
        tier_used=2,
        created_at=_now(),
    )
    decision = DecisionRecord(
        decision_id="d-emb-001",
        case_id="c-emb-001",
        decision="decline",
        final_risk_score=0.85,
        decided_by="tier2",
        decided_at=_now(),
    )
    reasoning = ReasoningRecord(
        reasoning_id="r-emb-001",
        case_id="c-emb-001",
        internal_view="high risk",
        audit_view="declined",
        customer_view="declined by policy",
        token_cost=500,
        model_used="claude-opus-4-6",
        created_at=_now(),
    )
    embedding = [0.1] * 384
    result = await store.store_case(
        case=case, decision=decision, reasoning=reasoning, embedding=embedding
    )
    assert result == "c-emb-001"
    assert "c-emb-001" in store._case_to_embedding


@pytest.mark.asyncio
async def test_store_case_with_policy_snapshot(store: ReasoningBankStore) -> None:
    case = CaseRecord(
        case_id="c-pol-001",
        event_type="aml",
        product="payments",
        jurisdiction="EU",
        customer_id="cust-pol",
        risk_context={},
        playbook_id="pb-aml-v3",
        tier_used=1,
        created_at=_now(),
    )
    decision = DecisionRecord(
        decision_id="d-pol-001",
        case_id="c-pol-001",
        decision="approve",
        final_risk_score=0.2,
        decided_by="tier1",
        decided_at=_now(),
    )
    reasoning = ReasoningRecord(
        reasoning_id="r-pol-001",
        case_id="c-pol-001",
        internal_view="low risk",
        audit_view="approved",
        customer_view="processed",
        token_cost=300,
        model_used="claude-haiku-4-5",
        created_at=_now(),
    )
    policy = PolicySnapshot(
        snapshot_id="ps-001",
        case_id="c-pol-001",
        playbook_id="pb-aml-v3",
        playbook_version="v3",
        policy_hash="abc123",
        captured_at=_now(),
    )
    await store.store_case(case=case, decision=decision, reasoning=reasoning, policy=policy)
    assert "ps-001" in store._policy_snapshots


# ── Store: get_reusable_reasoning ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reusable_reasoning_returns_reasoning(store: ReasoningBankStore) -> None:
    case = CaseRecord(
        case_id="c-reuse-001",
        event_type="aml",
        product="emoney",
        jurisdiction="UK",
        customer_id="cust-reuse",
        risk_context={},
        playbook_id="pb-v1",
        tier_used=1,
        created_at=_now(),
    )
    decision = DecisionRecord(
        decision_id="d-reuse-001",
        case_id="c-reuse-001",
        decision="approve",
        final_risk_score=0.3,
        decided_by="tier1",
        decided_at=_now(),
    )
    reasoning = ReasoningRecord(
        reasoning_id="r-reuse-001",
        case_id="c-reuse-001",
        internal_view="low risk signal",
        audit_view="auto-approved",
        customer_view="payment processed",
        token_cost=200,
        model_used="claude-sonnet-4-6",
        created_at=_now(),
    )
    await store.store_case(case=case, decision=decision, reasoning=reasoning)
    result = await store.get_reusable_reasoning("c-reuse-001")
    assert result is not None
    assert result.case_id == "c-reuse-001"
    assert result.internal_view == "low risk signal"


@pytest.mark.asyncio
async def test_get_reusable_reasoning_not_found_returns_none(store: ReasoningBankStore) -> None:
    result = await store.get_reusable_reasoning("c-nonexistent")
    assert result is None


# ── Store: find_similar ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_similar_returns_empty_when_no_embeddings(store: ReasoningBankStore) -> None:
    results = await store.find_similar(query_vector=[0.1] * 384)
    assert results == []


@pytest.mark.asyncio
async def test_find_similar_with_high_similarity_returns_case(store: ReasoningBankStore) -> None:
    """Store a case with a known vector, then query with same vector → should find it."""
    case = CaseRecord(
        case_id="c-sim-001",
        event_type="aml",
        product="emoney",
        jurisdiction="UK",
        customer_id="cust-sim",
        risk_context={},
        playbook_id="pb-v1",
        tier_used=1,
        created_at=_now(),
    )
    decision = DecisionRecord(
        decision_id="d-sim-001",
        case_id="c-sim-001",
        decision="approve",
        final_risk_score=0.2,
        decided_by="tier1",
        decided_at=_now(),
    )
    reasoning = ReasoningRecord(
        reasoning_id="r-sim-001",
        case_id="c-sim-001",
        internal_view="v",
        audit_view="v",
        customer_view="v",
        token_cost=100,
        model_used="claude-sonnet-4-6",
        created_at=_now(),
    )
    # Uniform vector of 1/sqrt(384) is normalised → cosine similarity to itself = 1.0
    vector = [1.0] * 384
    await store.store_case(case=case, decision=decision, reasoning=reasoning, embedding=vector)
    results = await store.find_similar(query_vector=vector, top_k=5, threshold=0.0)
    assert len(results) >= 1
    assert results[0].case_id == "c-sim-001"


# ── Store: record_feedback ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_feedback_stores_feedback(store: ReasoningBankStore) -> None:
    feedback = FeedbackRecord(
        feedback_id="fb-001",
        case_id="c-001",
        feedback_type="false_positive",
        provided_by="mlro-001",
        note="Transaction was legitimate international transfer.",
        recorded_at=_now(),
    )
    await store.record_feedback(feedback)
    assert any(f.feedback_id == "fb-001" for f in store._feedback)


# ── Store: compute_policy_hash ────────────────────────────────────────────────


def test_compute_policy_hash_returns_string(store: ReasoningBankStore) -> None:
    h = store.compute_policy_hash("pb-aml-v2")
    assert isinstance(h, str)
    assert len(h) > 0


def test_compute_policy_hash_deterministic(store: ReasoningBankStore) -> None:
    h1 = store.compute_policy_hash("pb-aml-v2")
    h2 = store.compute_policy_hash("pb-aml-v2")
    assert h1 == h2


def test_compute_policy_hash_different_ids_differ(store: ReasoningBankStore) -> None:
    h1 = store.compute_policy_hash("pb-aml-v1")
    h2 = store.compute_policy_hash("pb-aml-v2")
    assert h1 != h2


# ── API: POST /reasoning/store ────────────────────────────────────────────────


def test_api_store_case_returns_201() -> None:
    resp = client.post("/reasoning/store", json=_store_payload())
    assert resp.status_code == 201


def test_api_store_case_returns_case_id() -> None:
    resp = client.post("/reasoning/store", json=_store_payload("case-api-001"))
    data = resp.json()
    assert data["case_id"] == "case-api-001"
    assert "stored_at" in data


def test_api_store_case_with_embedding() -> None:
    payload = _store_payload("case-emb-001")
    payload["embedding"] = [0.1] * 10
    resp = client.post("/reasoning/store", json=payload)
    assert resp.status_code == 201


# ── API: POST /reasoning/similar ──────────────────────────────────────────────


def test_api_find_similar_returns_200() -> None:
    resp = client.post(
        "/reasoning/similar",
        json={"query_vector": [0.1] * 10, "top_k": 5, "threshold": 0.85},
    )
    assert resp.status_code == 200


def test_api_find_similar_returns_cases_list() -> None:
    resp = client.post(
        "/reasoning/similar",
        json={"query_vector": [0.1] * 10},
    )
    data = resp.json()
    assert "cases" in data
    assert isinstance(data["cases"], list)


# ── API: POST /reasoning/reuse ────────────────────────────────────────────────


def test_api_reuse_not_found_returns_reusable_false() -> None:
    resp = client.post("/reasoning/reuse", json={"case_id": "case-nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reusable"] is False


def test_api_reuse_existing_case_returns_reasoning(fresh_store: ReasoningBankStore) -> None:
    # Store a case first via API
    payload = _store_payload("case-reuse-001")
    client.post("/reasoning/store", json=payload)
    # Now reuse it
    resp = client.post("/reasoning/reuse", json={"case_id": "case-reuse-001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reusable"] is True
    assert data["case_id"] == "case-reuse-001"
    assert data["internal_view"] == payload["internal_reasoning"]


# ── API: GET /reasoning/{case_id}/explain/{view} ──────────────────────────────


def test_api_explain_invalid_view_returns_400() -> None:
    resp = client.get("/reasoning/case-001/explain/unknown_view")
    assert resp.status_code == 400
    assert "view must be" in resp.json()["detail"]


def test_api_explain_not_found_returns_404() -> None:
    resp = client.get("/reasoning/case-nonexistent/explain/audit")
    assert resp.status_code == 404


def test_api_explain_audit_view_returns_200(fresh_store: ReasoningBankStore) -> None:
    payload = _store_payload("case-explain-001")
    client.post("/reasoning/store", json=payload)
    resp = client.get("/reasoning/case-explain-001/explain/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["view"] == "audit"
    assert data["content"] == payload["audit_reasoning"]


def test_api_explain_customer_view_returns_200(fresh_store: ReasoningBankStore) -> None:
    payload = _store_payload("case-explain-002")
    client.post("/reasoning/store", json=payload)
    resp = client.get("/reasoning/case-explain-002/explain/customer")
    assert resp.status_code == 200
    data = resp.json()
    assert data["view"] == "customer"


def test_api_explain_internal_view_returns_200(fresh_store: ReasoningBankStore) -> None:
    payload = _store_payload("case-explain-003")
    client.post("/reasoning/store", json=payload)
    resp = client.get("/reasoning/case-explain-003/explain/internal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["view"] == "internal"


# ── API: POST /reasoning/feedback ─────────────────────────────────────────────


def test_api_feedback_valid_type_returns_201() -> None:
    resp = client.post(
        "/reasoning/feedback",
        json={
            "case_id": "case-001",
            "feedback_type": "false_positive",
            "provided_by": "mlro-001",
            "note": "Transaction was legitimate.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "feedback_id" in data
    assert data["case_id"] == "case-001"


def test_api_feedback_invalid_type_returns_400() -> None:
    resp = client.post(
        "/reasoning/feedback",
        json={
            "case_id": "case-001",
            "feedback_type": "invalid_type",
            "provided_by": "mlro-001",
            "note": "Some note.",
        },
    )
    assert resp.status_code == 400
    assert "feedback_type" in resp.json()["detail"]


def test_api_feedback_sar_filed_type_accepted() -> None:
    resp = client.post(
        "/reasoning/feedback",
        json={
            "case_id": "case-002",
            "feedback_type": "sar_filed",
            "provided_by": "mlro-002",
            "note": "SAR ref: SAR-2026-002.",
        },
    )
    assert resp.status_code == 201
