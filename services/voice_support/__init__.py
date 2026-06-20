"""
services/voice_support — Voice-AI support channel (GAP-069, IMPL-3).

LiveKit/Pipecat gateway + Faster-Whisper ASR + TTS + Presidio PII redaction +
consent-gated recording, routed into support ticketing with an append-only
ClickHouse audit and MLRO HITL on flagged calls (ADR-112; ties GAP-038/039).
Advisory/support only — NO autonomous financial execution via voice (ADR-049).
"""

from __future__ import annotations

from services.voice_support.models import (
    Speaker,
    TranscriptSegment,
    VoiceSession,
    VoiceSessionSummary,
)
from services.voice_support.service import VoiceSupportError, VoiceSupportService

__all__ = [
    "Speaker",
    "TranscriptSegment",
    "VoiceSession",
    "VoiceSessionSummary",
    "VoiceSupportError",
    "VoiceSupportService",
]
