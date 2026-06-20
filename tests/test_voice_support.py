"""
tests/test_voice_support.py — IMPL-3 voice-AI support channel (GAP-069)

Gateway safe-stub, ASR fake, PII redaction (before storage), consent-gate
(no recording without consent), routing to ticket, and MLRO HITL on flagged call.
Reuses real EventStore / HITLService / InMemoryTicketStore (in-memory).
"""

from __future__ import annotations

from services.audit_trail.event_store import EventStore
from services.hitl.hitl_port import CaseStatus as HITLCaseStatus
from services.hitl.hitl_service import HITLService
from services.support.support_models import InMemoryTicketStore
from services.voice_support.asr import FasterWhisperAsr
from services.voice_support.gateway import LiveKitPipecatGateway
from services.voice_support.models import Speaker
from services.voice_support.pii import PresidioRedactor
from services.voice_support.service import VoiceSupportService


class _FakeAsr:
    def __init__(self, text: str) -> None:
        self._text = text

    def transcribe(self, audio: bytes) -> str:
        return self._text


def _service(
    asr: _FakeAsr | None = None,
    audit: EventStore | None = None,
    hitl: HITLService | None = None,
    tickets: InMemoryTicketStore | None = None,
) -> VoiceSupportService:
    return VoiceSupportService(
        asr=asr,
        audit=audit or EventStore(),
        hitl=hitl or HITLService(),
        ticket_store=tickets or InMemoryTicketStore(),
    )


class TestGatewaySafeStub:
    def test_unconfigured_gateway_mints_local_ref_no_secrets(self) -> None:
        ref = LiveKitPipecatGateway(livekit_url="").start_call("cust-1")
        assert ref.startswith("voice-cust-1-")


class TestAsrSafeStub:
    def test_unconfigured_whisper_returns_empty(self) -> None:
        assert FasterWhisperAsr(model_name="").transcribe(b"\x00\x01") == ""


class TestPiiRedaction:
    def test_email_phone_card_redacted(self) -> None:
        red = PresidioRedactor(use_presidio=False).redact(
            "email me at john@acme.com or call +44 7700 900123, card 4111 1111 1111 1111"
        )
        assert "john@acme.com" not in red
        assert "4111 1111 1111 1111" not in red
        assert "<REDACTED:EMAIL>" in red

    def test_transcript_stored_redacted(self) -> None:
        svc = _service()
        session = svc.start_session("cust-1", consent_to_record=True)
        seg = svc.add_transcript(session.session_id, Speaker.CUSTOMER, "my email is a@b.com")
        assert "a@b.com" not in seg.redacted_text
        assert "<REDACTED:EMAIL>" in seg.redacted_text


class TestConsentGate:
    def test_no_consent_no_recording(self) -> None:
        svc = _service()
        session = svc.start_session("cust-1", consent_to_record=False)
        assert session.recording_allowed is False
        assert session.retention_until is None

    def test_consent_enables_recording_with_retention(self) -> None:
        svc = _service()
        session = svc.start_session("cust-1", consent_to_record=True)
        assert session.recording_allowed is True
        assert session.retention_until is not None


class TestEndSessionRouting:
    async def test_routes_to_ticket(self) -> None:
        tickets = InMemoryTicketStore()
        svc = _service(tickets=tickets)
        session = svc.start_session("cust-1", consent_to_record=True)
        svc.add_transcript(session.session_id, Speaker.CUSTOMER, "hello, balance question")
        summary = await svc.end_session(session.session_id)
        assert summary.ticket_id
        assert summary.flagged is False
        assert summary.hitl_case_id is None
        assert await tickets.get(summary.ticket_id) is not None

    async def test_transcribe_audio_via_fake_asr(self) -> None:
        svc = _service(asr=_FakeAsr("just a normal enquiry"))
        session = svc.start_session("cust-1", consent_to_record=True)
        seg = svc.transcribe_audio(session.session_id, Speaker.CUSTOMER, b"\x00")
        assert seg.redacted_text == "just a normal enquiry"


class TestHITLOnFlag:
    async def test_flagged_call_enqueues_mlro_no_auto_clear(self) -> None:
        hitl = HITLService()
        svc = _service(hitl=hitl)
        session = svc.start_session("cust-1", consent_to_record=True)
        svc.add_transcript(
            session.session_id, Speaker.CUSTOMER, "this is fraud, my card was stolen"
        )
        summary = await svc.end_session(session.session_id)
        assert summary.flagged is True
        assert summary.hitl_case_id is not None
        case = hitl.get_case(summary.hitl_case_id)
        assert case is not None
        assert case.status is HITLCaseStatus.PENDING  # mandatory review, not auto-cleared

    async def test_clean_call_no_hitl(self) -> None:
        hitl = HITLService()
        svc = _service(hitl=hitl)
        session = svc.start_session("cust-1", consent_to_record=True)
        svc.add_transcript(session.session_id, Speaker.AGENT, "your balance is updated")
        summary = await svc.end_session(session.session_id)
        assert summary.flagged is False
        assert summary.hitl_case_id is None


def test_voice_cannot_execute_financial() -> None:
    from services.voice_support.service import VOICE_CAN_EXECUTE_FINANCIAL

    assert VOICE_CAN_EXECUTE_FINANCIAL is False
