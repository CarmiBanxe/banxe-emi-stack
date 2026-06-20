"""
api/models/voice_support.py — Voice-AI support API DTOs
GAP-069 | IMPL-3 | banxe-emi-stack
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    customer_id: str = Field(..., description="Customer on the call")
    consent_to_record: bool = Field(
        ..., description="Explicit consent to record — mandatory; false ⇒ no audio stored"
    )


class StartSessionResponse(BaseModel):
    session_id: str
    recording_allowed: bool
    retention_until: str | None = None


class TranscriptRequest(BaseModel):
    speaker: str = Field(..., description="CUSTOMER | AGENT")
    text: str = Field(..., description="Raw transcript turn (PII-redacted before storage)")


class TranscriptResponse(BaseModel):
    redacted_text: str


class EndSessionResponse(BaseModel):
    session_id: str
    ticket_id: str
    flagged: bool
    recording_retained: bool
    segment_count: int
    redacted_transcript: str
    hitl_case_id: str | None = None
