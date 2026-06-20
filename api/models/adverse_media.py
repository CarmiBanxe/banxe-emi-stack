"""
api/models/adverse_media.py — Adverse-media screening API DTOs
GAP-064 | IMPL-1 | banxe-emi-stack
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenRequest(BaseModel):
    customer_id: str = Field(..., description="Customer to screen for adverse media")


class HitModel(BaseModel):
    subject_name: str
    headline: str
    source: str
    categories: list[str]
    composite_score: float
    confidence: str
    url: str | None = None


class ScreenResponse(BaseModel):
    customer_id: str
    screened_at: str
    action: str  # CLEAR | HITL_REVIEW
    risk: str  # NONE | LOW | MEDIUM | HIGH
    hits: list[HitModel]
    marble_case_id: str | None = None
    hitl_case_id: str | None = None
