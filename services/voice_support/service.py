"""
services/voice_support/service.py — VoiceSupportService orchestration
GAP-069 | IMPL-3 | banxe-emi-stack

Orchestrates the voice gateway + ASR + TTS + PII redaction + recording policy for
the voice-AI support channel (ADR-112; ties GAP-038/039). Routes the call into
support ticketing (reuse), appends an append-only ClickHouse audit, and raises an
MLRO/Compliance HITL review on compliance-flagged calls.

Guardrails: consent-to-record mandatory (no recording/audio-store without consent);
transcripts PII-redacted before any persistence (UK GDPR); advisory/support only —
NO autonomous financial execution via voice (ADR-049 needs HITL + biometric).
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid

from services.audit_trail.event_store import EventStore
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    SourceSystem,
)
from services.hitl.hitl_port import ReviewReason
from services.hitl.hitl_service import HITLService
from services.support.support_models import (
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStorePort,
)
from services.voice_support.asr import FasterWhisperAsr
from services.voice_support.gateway import LiveKitPipecatGateway
from services.voice_support.models import (
    AsrPort,
    PiiRedactorPort,
    Speaker,
    TelephonyGatewayPort,
    TranscriptSegment,
    TtsPort,
    VoiceSession,
    VoiceSessionSummary,
)
from services.voice_support.pii import PresidioRedactor
from services.voice_support.recording import RecordingPolicy
from services.voice_support.tts import XttsTts

logger = logging.getLogger(__name__)

# Compliance keywords that flag a call for MLRO / Compliance review.
_FLAG_KEYWORDS = frozenset({"fraud", "scam", "complaint", "sar", "launder", "stolen", "dispute"})

# This channel is advisory/support only — there is no financial-execution path.
VOICE_CAN_EXECUTE_FINANCIAL = False


class VoiceSupportError(Exception):
    """Raised on an unknown / closed voice session."""


class VoiceSupportService:
    """Voice-AI support channel orchestrator."""

    def __init__(
        self,
        *,
        gateway: TelephonyGatewayPort | None = None,
        asr: AsrPort | None = None,
        tts: TtsPort | None = None,
        pii: PiiRedactorPort | None = None,
        recording_policy: RecordingPolicy | None = None,
        ticket_store: TicketStorePort | None = None,
        audit: EventStore | None = None,
        hitl: HITLService | None = None,
    ) -> None:
        self._gateway: TelephonyGatewayPort = gateway or LiveKitPipecatGateway()
        self._asr: AsrPort = asr or FasterWhisperAsr()
        self._tts: TtsPort = tts or XttsTts()
        self._pii: PiiRedactorPort = pii or PresidioRedactor()
        self._recording = recording_policy or RecordingPolicy()
        self._tickets: TicketStorePort = ticket_store or InMemoryTicketStore()
        self._audit = audit or EventStore()
        self._hitl = hitl or HITLService()
        self._sessions: dict[str, VoiceSession] = {}

    def start_session(
        self, customer_id: str, *, consent_to_record: bool, actor_id: str = "voice-agent"
    ) -> VoiceSession:
        now = datetime.now(UTC)
        decision = self._recording.authorize(consent_to_record=consent_to_record, now=now)
        gateway_ref = self._gateway.start_call(customer_id)
        session = VoiceSession(
            session_id=str(uuid.uuid4()),
            customer_id=customer_id,
            consent_to_record=consent_to_record,
            started_at=now,
            gateway_ref=gateway_ref,
            recording_allowed=decision.allowed,
            retention_until=decision.retention_until,
        )
        self._sessions[session.session_id] = session
        self._audit.append(
            category=EventCategory.COMPLIANCE,
            severity=EventSeverity.INFO,
            action=AuditAction.CREATE,
            entity_type="voice_session",
            entity_id=session.session_id,
            actor_id=actor_id,
            details={
                "event": "voice_session_start",
                "customer_id": customer_id,
                "consent_to_record": consent_to_record,
                "recording_allowed": decision.allowed,
            },
            source=SourceSystem.API,
        )
        return session

    def add_transcript(self, session_id: str, speaker: Speaker, raw_text: str) -> TranscriptSegment:
        session = self._require_session(session_id)
        # PII redaction BEFORE storage — the raw text is never retained.
        redacted = self._pii.redact(raw_text)
        segment = TranscriptSegment(speaker=speaker, redacted_text=redacted, at=datetime.now(UTC))
        session.segments.append(segment)
        if _is_flagged(raw_text):
            session.flagged = True
        return segment

    def transcribe_audio(
        self, session_id: str, speaker: Speaker, audio: bytes
    ) -> TranscriptSegment:
        text = self._asr.transcribe(audio)
        return self.add_transcript(session_id, speaker, text)

    async def end_session(
        self, session_id: str, *, actor_id: str = "voice-agent"
    ) -> VoiceSessionSummary:
        session = self._require_session(session_id)
        self._gateway.end_call(session.gateway_ref)
        transcript = "\n".join(f"{s.speaker.value}: {s.redacted_text}" for s in session.segments)

        priority = TicketPriority.HIGH if session.flagged else TicketPriority.MEDIUM
        category = TicketCategory.FRAUD if session.flagged else TicketCategory.GENERAL
        ticket = SupportTicket.create(
            customer_id=session.customer_id,
            subject=f"Voice support call {session.session_id}",
            body=transcript or "(no transcript)",
            category=category,
            priority=priority,
            channel="VOICE",
        )
        await self._tickets.save(ticket)

        hitl_case_id: str | None = None
        if session.flagged:
            hitl_case_id = self._enqueue_mlro(session, ticket.id)

        self._audit.append(
            category=EventCategory.COMPLIANCE,
            severity=EventSeverity.WARNING if session.flagged else EventSeverity.INFO,
            action=AuditAction.UPDATE,
            entity_type="voice_session",
            entity_id=session.session_id,
            actor_id=actor_id,
            details={
                "event": "voice_session_end",
                "ticket_id": ticket.id,
                "flagged": session.flagged,
                "hitl_case_id": hitl_case_id,
                "recording_retained": session.recording_allowed,
                "segments": len(session.segments),
            },
            source=SourceSystem.API,
        )
        del self._sessions[session_id]
        return VoiceSessionSummary(
            session_id=session.session_id,
            customer_id=session.customer_id,
            ticket_id=ticket.id,
            flagged=session.flagged,
            recording_retained=session.recording_allowed,
            segment_count=len(session.segments),
            redacted_transcript=transcript,
            retention_until=session.retention_until,
            hitl_case_id=hitl_case_id,
        )

    def _enqueue_mlro(self, session: VoiceSession, ticket_id: str) -> str:
        from decimal import Decimal

        case = self._hitl.enqueue(
            transaction_id=f"voice:{session.session_id}",
            customer_id=session.customer_id,
            entity_type="voice_session",
            amount=Decimal("0"),
            currency="GBP",
            reasons=[ReviewReason.AML_COMBINED],
            fraud_score=0,
            fraud_risk="FLAGGED",
            aml_flags=[f"VOICE_FLAG:ticket:{ticket_id}"],
            hold_reasons=["Voice call compliance-flagged — mandatory MLRO review (no auto-clear)"],
        )
        return case.case_id

    def _require_session(self, session_id: str) -> VoiceSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise VoiceSupportError(f"unknown or closed voice session: {session_id}")
        return session


def _is_flagged(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _FLAG_KEYWORDS)
