"""
services/reasoning_bank/api.py — ReasoningBank FastAPI Router
IL-ARL-01 | banxe-emi-stack

Exposes ReasoningBank operations as REST endpoints:
  POST /reasoning/store
  POST /reasoning/similar
  POST /reasoning/reuse
  GET  /reasoning/{case_id}/explain/{view}

GDPR Art.22: three explanation views (audit, customer, internal).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.reasoning_bank.models import (
    CaseRecord,
    DecisionRecord,
    FeedbackRecord,
    PolicySnapshot,
    ReasoningRecord,
)
from services.reasoning_bank.store import ReasoningBankStore

router = APIRouter(prefix="/reasoning", tags=["reasoning_bank"])

# Singleton store — in production inject via FastAPI dependency
_store = ReasoningBankStore()


def get_store() -> ReasoningBankStore:
    return _store


# ── Request / Response Models ─────────────────────────────────────────────────


class StoreRequest(BaseModel):
    case_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    product: str
    jurisdiction: str
    customer_id: str
    risk_context: dict[str, Any]
    playbook_id: str
    tier_used: int
    decision: str
    final_risk_score: float
    decided_by: str
    internal_reasoning: str
    audit_reasoning: str
    customer_reasoning: str
    token_cost: int
    model_used: str
    embedding: list[float] | None = None
    playbook_version: str = "v1"
    policy_hash: str = ""


class StoreResponse(BaseModel):
    case_id: str
    stored_at: str


class SimilarRequest(BaseModel):
    query_vector: list[float]
    top_k: int = 5
    threshold: float = 0.85


class SimilarCase(BaseModel):
    case_id: str
    event_type: str
    product: str
    jurisdiction: str
    playbook_id: str
    tier_used: int
    created_at: str


class SimilarResponse(BaseModel):
    cases: list[SimilarCase]


class ReuseRequest(BaseModel):
    case_id: str


class ReuseResponse(BaseModel):
    case_id: str
    reasoning_id: str
    internal_view: str
    audit_view: str
    customer_view: str
    token_cost: int
    reusable: bool


class ExplainResponse(BaseModel):
    case_id: str
    view: str
    content: str
    generated_at: str


class FeedbackRequest(BaseModel):
    case_id: str
    feedback_type: str
    provided_by: str
    note: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/store", response_model=StoreResponse, status_code=201)
async def store_case(
    req: StoreRequest,
    store: ReasoningBankStore = Depends(get_store),
) -> StoreResponse:
    """Store a compliance case with its decision and reasoning.

    Persists the full case envelope, decision record, structured reasoning,
    and optional embedding vector for future similarity search.
    """
    now = datetime.now(UTC)
    case = CaseRecord(
        case_id=req.case_id,
        event_type=req.event_type,
        product=req.product,
        jurisdiction=req.jurisdiction,
        customer_id=req.customer_id,
        risk_context=req.risk_context,
        playbook_id=req.playbook_id,
        tier_used=req.tier_used,
        created_at=now,
    )
    decision = DecisionRecord(
        decision_id=str(uuid.uuid4()),
        case_id=req.case_id,
        decision=req.decision,
        final_risk_score=req.final_risk_score,
        decided_by=req.decided_by,
        decided_at=now,
    )
    reasoning = ReasoningRecord(
        reasoning_id=str(uuid.uuid4()),
        case_id=req.case_id,
        internal_view=req.internal_reasoning,
        audit_view=req.audit_reasoning,
        customer_view=req.customer_reasoning,
        token_cost=req.token_cost,
        model_used=req.model_used,
        created_at=now,
    )
    policy = PolicySnapshot(
        snapshot_id=str(uuid.uuid4()),
        case_id=req.case_id,
        playbook_id=req.playbook_id,
        playbook_version=req.playbook_version,
        policy_hash=req.policy_hash or store.compute_policy_hash(req.playbook_id),
        captured_at=now,
    )
    await store.store_case(
        case=case,
        decision=decision,
        reasoning=reasoning,
        embedding=req.embedding,
        policy=policy,
    )
    return StoreResponse(case_id=req.case_id, stored_at=now.isoformat())


@router.post("/similar", response_model=SimilarResponse)
async def find_similar(
    req: SimilarRequest,
    store: ReasoningBankStore = Depends(get_store),
) -> SimilarResponse:
    """Find cases similar to the given embedding vector.

    Returns top-k cases above the similarity threshold.
    """
    cases = await store.find_similar(
        query_vector=req.query_vector,
        top_k=req.top_k,
        threshold=req.threshold,
    )
    return SimilarResponse(
        cases=[
            SimilarCase(
                case_id=c.case_id,
                event_type=c.event_type,
                product=c.product,
                jurisdiction=c.jurisdiction,
                playbook_id=c.playbook_id,
                tier_used=c.tier_used,
                created_at=c.created_at.isoformat(),
            )
            for c in cases
        ]
    )


@router.post("/reuse", response_model=ReuseResponse)
async def reuse_reasoning(
    req: ReuseRequest,
    store: ReasoningBankStore = Depends(get_store),
) -> ReuseResponse:
    """Return reusable reasoning for a given case_id.

    Returns reusable=False if the reasoning is disqualified
    (overridden decision, feedback flagging false positive).
    """
    reasoning = await store.get_reusable_reasoning(req.case_id)
    if reasoning is None:
        return ReuseResponse(
            case_id=req.case_id,
            reasoning_id="",
            internal_view="",
            audit_view="",
            customer_view="",
            token_cost=0,
            reusable=False,
        )
    return ReuseResponse(
        case_id=req.case_id,
        reasoning_id=reasoning.reasoning_id,
        internal_view=reasoning.internal_view,
        audit_view=reasoning.audit_view,
        customer_view=reasoning.customer_view,
        token_cost=reasoning.token_cost,
        reusable=True,
    )


@router.get("/{case_id}/explain/{view}", response_model=ExplainResponse)
async def explain(
    case_id: str,
    view: str,
    store: ReasoningBankStore = Depends(get_store),
) -> ExplainResponse:
    """Get an explanation for a compliance decision (GDPR Art.22).

    view must be one of: audit, customer, internal.
    """
    if view not in ("audit", "customer", "internal"):
        raise HTTPException(status_code=400, detail="view must be: audit | customer | internal")
    reasoning = await store.get_reusable_reasoning(case_id)
    if reasoning is None:
        raise HTTPException(status_code=404, detail=f"No reasoning found for case {case_id!r}")
    match view:
        case "internal":
            content = reasoning.internal_view
        case "audit":
            content = reasoning.audit_view
        case "customer":
            content = reasoning.customer_view
        case _:
            content = ""
    return ExplainResponse(
        case_id=case_id,
        view=view,
        content=content,
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.post("/feedback", status_code=201)
async def record_feedback(
    req: FeedbackRequest,
    store: ReasoningBankStore = Depends(get_store),
) -> dict[str, str]:
    """Record late outcome feedback for a case (I-27: write-only corpus)."""
    valid_types = {"false_positive", "false_negative", "sar_filed", "dispute"}
    if req.feedback_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"feedback_type must be one of {valid_types}",
        )
    feedback = FeedbackRecord(
        feedback_id=str(uuid.uuid4()),
        case_id=req.case_id,
        feedback_type=req.feedback_type,
        provided_by=req.provided_by,
        note=req.note,
        recorded_at=datetime.now(UTC),
    )
    await store.record_feedback(feedback)
    return {"feedback_id": feedback.feedback_id, "case_id": req.case_id}
