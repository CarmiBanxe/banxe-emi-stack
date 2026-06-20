"""
services/voice_support/models.py — Voice-AI support domain models + ports
GAP-069 | IMPL-3 | banxe-emi-stack

Voice-AI support channel (ADR-112; ties GAP-038/039). Advisory/support only —
NO autonomous financial execution via voice (ADR-049: needs HITL + biometric).
Consent-to-record is mandatory; transcripts are PII-redacted before any storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


class Speaker(str, Enum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"


@dataclass(frozen=True)
class TranscriptSegment:
    """One turn of conversation — only the PII-redacted text is ever retained."""

    speaker: Speaker
    redacted_text: str
    at: datetime


@dataclass
class VoiceSession:
    """Live voice-support session state (in-memory; no raw audio persisted)."""

    session_id: str
    customer_id: str
    consent_to_record: bool
    started_at: datetime
    gateway_ref: str
    recording_allowed: bool
    retention_until: datetime | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    flagged: bool = False


@dataclass(frozen=True)
class VoiceSessionSummary:
    session_id: str
    customer_id: str
    ticket_id: str
    flagged: bool
    recording_retained: bool
    segment_count: int
    redacted_transcript: str
    retention_until: datetime | None = None
    hitl_case_id: str | None = None


@dataclass(frozen=True)
class RecordingDecision:
    allowed: bool
    retention_until: datetime | None = None
    reason: str = ""


class TelephonyGatewayPort(Protocol):
    """LiveKit/Pipecat + SIP realtime gateway. No secrets in code."""

    def start_call(self, customer_id: str) -> str: ...

    def end_call(self, gateway_ref: str) -> None: ...


class AsrPort(Protocol):
    """Speech-to-text (Faster-Whisper)."""

    def transcribe(self, audio: bytes) -> str: ...


class TtsPort(Protocol):
    """Text-to-speech (XTTS / Kokoro)."""

    def synthesize(self, text: str) -> bytes: ...


class PiiRedactorPort(Protocol):
    """Presidio-style PII redaction applied before any persistence (UK GDPR)."""

    def redact(self, text: str) -> str: ...
