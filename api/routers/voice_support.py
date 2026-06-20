"""
api/routers/voice_support.py — Voice-AI support endpoints
GAP-069 | IMPL-3 | banxe-emi-stack

POST /v1/support/voice/session                 — start a consent-gated session
POST /v1/support/voice/session/{id}/transcript — add a PII-redacted transcript turn
POST /v1/support/voice/session/{id}/end        — end → route to ticket (+ HITL on flag)
ADR-112. Consent-to-record mandatory; transcripts redacted before storage.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from api.models.voice_support import (
    EndSessionResponse,
    StartSessionRequest,
    StartSessionResponse,
    TranscriptRequest,
    TranscriptResponse,
)
from services.voice_support.models import Speaker
from services.voice_support.service import VoiceSupportError, VoiceSupportService

router = APIRouter(tags=["Voice-AI Support"])


@lru_cache(maxsize=1)
def _get_service() -> VoiceSupportService:
    return VoiceSupportService()


@router.post("/support/voice/session", response_model=StartSessionResponse)
def start_session(req: StartSessionRequest) -> StartSessionResponse:
    session = _get_service().start_session(req.customer_id, consent_to_record=req.consent_to_record)
    return StartSessionResponse(
        session_id=session.session_id,
        recording_allowed=session.recording_allowed,
        retention_until=(session.retention_until.isoformat() if session.retention_until else None),
    )


@router.post("/support/voice/session/{session_id}/transcript", response_model=TranscriptResponse)
def add_transcript(session_id: str, req: TranscriptRequest) -> TranscriptResponse:
    try:
        segment = _get_service().add_transcript(session_id, Speaker(req.speaker), req.text)
    except VoiceSupportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TranscriptResponse(redacted_text=segment.redacted_text)


@router.post("/support/voice/session/{session_id}/end", response_model=EndSessionResponse)
async def end_session(session_id: str) -> EndSessionResponse:
    try:
        summary = await _get_service().end_session(session_id)
    except VoiceSupportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EndSessionResponse(
        session_id=summary.session_id,
        ticket_id=summary.ticket_id,
        flagged=summary.flagged,
        recording_retained=summary.recording_retained,
        segment_count=summary.segment_count,
        redacted_transcript=summary.redacted_transcript,
        hitl_case_id=summary.hitl_case_id,
    )
