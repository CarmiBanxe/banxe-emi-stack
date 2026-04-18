"""
api/routers/risk_management.py — Risk Management & Scoring Engine REST endpoints
IL-RMS-01 | Phase 37 | banxe-emi-stack

9 REST endpoints under /v1/risk/
I-01: All scores as strings in responses (I-05).
I-27: Threshold changes return HITL proposal.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.risk_management.models import (
    RiskCategory,
    RiskThreshold,
)
from services.risk_management.risk_agent import HITLProposal, RiskAgent
from services.risk_management.risk_aggregator import RiskAggregator
from services.risk_management.risk_reporter import RiskReporter
from services.risk_management.risk_scorer import RiskScorer
from services.risk_management.threshold_manager import ThresholdManager

router = APIRouter(tags=["risk"])


@lru_cache(maxsize=1)
def _agent() -> RiskAgent:
    return RiskAgent()


@lru_cache(maxsize=1)
def _scorer() -> RiskScorer:
    return RiskScorer()


@lru_cache(maxsize=1)
def _aggregator() -> RiskAggregator:
    return RiskAggregator()


@lru_cache(maxsize=1)
def _threshold_mgr() -> ThresholdManager:
    return ThresholdManager()


@lru_cache(maxsize=1)
def _reporter() -> RiskReporter:
    return RiskReporter()


def _agent_dep() -> RiskAgent:
    return _agent()


def _scorer_dep() -> RiskScorer:
    return _scorer()


def _aggregator_dep() -> RiskAggregator:
    return _aggregator()


def _threshold_dep() -> ThresholdManager:
    return _threshold_mgr()


def _reporter_dep() -> RiskReporter:
    return _reporter()


def _hitl_to_dict(proposal: HITLProposal) -> dict:
    return {
        "status": "HITL_REQUIRED",
        "action": proposal.action,
        "resource_id": proposal.resource_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


# ── POST /v1/risk/score ───────────────────────────────────────────────────────


@router.post("/v1/risk/score", status_code=status.HTTP_201_CREATED)
def score_entity(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[RiskAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    """Score an entity for a given risk category."""
    try:
        category = RiskCategory(body["category"])
        factors = {k: Decimal(str(v)) for k, v in body.get("factors", {}).items()}
        return agent.process_scoring_request(body["entity_id"], factors, category)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/risk/entities/{entity_id}/scores ─────────────────────────────────


@router.get("/v1/risk/entities/{entity_id}/scores")
def get_entity_scores(
    entity_id: str,
    scorer: Annotated[RiskScorer, Depends(_scorer_dep)],
) -> list[dict[str, Any]]:
    """Get all risk scores for an entity."""
    scores = scorer._store.get_scores(entity_id)
    return [
        {
            "id": s.id,
            "entity_id": s.entity_id,
            "category": s.category.value,
            "score": str(s.score),
            "level": s.level.value,
            "model": s.model.value,
            "assessed_at": s.assessed_at.isoformat(),
        }
        for s in scores
    ]


# ── GET /v1/risk/entities/{entity_id}/assessment ─────────────────────────────


@router.get("/v1/risk/entities/{entity_id}/assessment")
def get_assessment(
    entity_id: str,
    aggregator: Annotated[RiskAggregator, Depends(_aggregator_dep)],
) -> dict[str, Any]:
    """Get risk assessment for an entity."""
    try:
        assessment = aggregator.aggregate_entity(entity_id)
        return {
            "id": assessment.id,
            "entity_id": assessment.entity_id,
            "status": assessment.status.value,
            "aggregate_score": str(assessment.aggregate_score),
            "score_count": len(assessment.scores),
            "created_at": assessment.created_at.isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/risk/portfolio/heatmap ──────────────────────────────────────────


@router.post("/v1/risk/portfolio/heatmap")
def get_portfolio_heatmap(
    body: Annotated[dict[str, Any], Body()],
    aggregator: Annotated[RiskAggregator, Depends(_aggregator_dep)],
) -> dict[str, Any]:
    """Get portfolio risk heatmap for a list of entities."""
    try:
        entity_ids = body.get("entity_ids", [])
        return aggregator.portfolio_heatmap(entity_ids)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/risk/portfolio/concentration ─────────────────────────────────────


@router.get("/v1/risk/portfolio/concentration")
def get_concentration(
    aggregator: Annotated[RiskAggregator, Depends(_aggregator_dep)],
) -> dict[str, Any]:
    """Get portfolio risk concentration analysis."""
    return aggregator.concentration_analysis()


# ── POST /v1/risk/thresholds/{category} ──────────────────────────────────────


@router.post("/v1/risk/thresholds/{category}")
def set_threshold(
    category: str,
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[ThresholdManager, Depends(_threshold_dep)],
) -> dict[str, Any]:
    """Propose a threshold change — always returns HITL proposal (I-27)."""
    try:
        cat = RiskCategory(category)
        threshold = RiskThreshold(
            category=cat,
            low_max=Decimal(str(body["low_max"])),
            medium_max=Decimal(str(body["medium_max"])),
            high_max=Decimal(str(body["high_max"])),
            alert_on_breach=body.get("alert_on_breach", True),
        )
        proposal = mgr.set_threshold(cat, threshold)
        return _hitl_to_dict(proposal)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/risk/thresholds ───────────────────────────────────────────────────


@router.get("/v1/risk/thresholds")
def list_thresholds(
    mgr: Annotated[ThresholdManager, Depends(_threshold_dep)],
) -> dict[str, Any]:
    """List all risk thresholds."""
    return mgr.list_thresholds()


# ── GET /v1/risk/mitigations/{plan_id} ───────────────────────────────────────


@router.get("/v1/risk/mitigations/{plan_id}")
def get_mitigation_plan(
    plan_id: str,
    agent: Annotated[RiskAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    """Get a mitigation plan by ID."""
    plan = agent._tracker.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return {
        "id": plan.id,
        "assessment_id": plan.assessment_id,
        "action": plan.action.value,
        "description": plan.description,
        "owner": plan.owner,
        "due_date": plan.due_date.isoformat(),
        "evidence_hash": plan.evidence_hash,
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
    }


# ── POST /v1/risk/reports ─────────────────────────────────────────────────────


@router.post("/v1/risk/reports", status_code=status.HTTP_201_CREATED)
def generate_report(
    body: Annotated[dict[str, Any], Body()],
    reporter: Annotated[RiskReporter, Depends(_reporter_dep)],
) -> dict[str, Any]:
    """Generate a risk report for a given scope and period."""
    try:
        from datetime import date

        period_start = date.fromisoformat(body["period_start"])
        period_end = date.fromisoformat(body["period_end"])
        report = reporter.generate_report(body["scope"], period_start, period_end)
        return {
            "id": report.id,
            "scope": report.scope,
            "total_entities": report.total_entities,
            "distribution": report.distribution,
            "top_risks": report.top_risks,
            "generated_at": report.generated_at.isoformat(),
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
