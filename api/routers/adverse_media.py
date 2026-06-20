"""
api/routers/adverse_media.py — Adverse-media screening endpoint
GAP-064 | IMPL-1 | banxe-emi-stack

POST /v1/compliance/adverse-media/screen {customer_id} -> {hits[], risk, action}
MLR 2017 Reg.28 EDD. Advisory output — adverse hits route to MLRO HITL (no auto-clear).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from api.models.adverse_media import HitModel, ScreenRequest, ScreenResponse
from services.adverse_media.service import AdverseMediaService
from services.customer.customer_port import CustomerManagementError
from services.customer.customer_service import get_customer_service

router = APIRouter(tags=["Adverse Media Screening"])


@lru_cache(maxsize=1)
def _get_service() -> AdverseMediaService:
    return AdverseMediaService(customer_service=get_customer_service())


@router.post("/compliance/adverse-media/screen", response_model=ScreenResponse)
def screen(req: ScreenRequest) -> ScreenResponse:
    try:
        result = _get_service().screen_customer(req.customer_id)
    except CustomerManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScreenResponse(
        customer_id=result.customer_id,
        screened_at=result.screened_at.isoformat(),
        action=result.action.value,
        risk=result.risk,
        hits=[
            HitModel(
                subject_name=h.article.subject_name,
                headline=h.article.headline,
                source=h.article.source,
                categories=h.article.categories,
                composite_score=float(h.composite_score),
                confidence=h.confidence.value,
                url=h.article.url,
            )
            for h in result.hits
        ],
        marble_case_id=result.marble_case_id,
        hitl_case_id=result.hitl_case_id,
    )
