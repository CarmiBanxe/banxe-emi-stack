"""
test_webhook_router.py — Centralised Webhook Router tests
S17-03 (partial): Unified inbound webhook handler with HMAC + audit
Pattern: Geniusto v5 webHookService / Handler incoming GCP
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from services.webhooks.webhook_router import (
    InMemoryWebhookAuditStore,
    WebhookProcessor,
    WebhookProvider,
    WebhookStatus,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _modulr_body(event_type: str = "PAYMENT_COMPLETED") -> bytes:
    return json.dumps({"eventType": event_type, "paymentId": "pay-001"}).encode()


def _modulr_sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _sumsub_body(event_type: str = "applicantReviewed") -> bytes:
    return json.dumps({"type": event_type, "applicantId": "app-001"}).encode()


def _sumsub_sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()


MODULR_SECRET = "test-modulr-secret"
SUMSUB_SECRET = "test-sumsub-secret"


@pytest.fixture
def processor():
    return WebhookProcessor(
        secrets={"modulr": MODULR_SECRET, "sumsub": SUMSUB_SECRET},
        audit_store=InMemoryWebhookAuditStore(),
    )


@pytest.fixture
def store():
    return InMemoryWebhookAuditStore()


# ── Modulr webhooks ────────────────────────────────────────────────────────────

class TestModulrWebhook:
    def test_valid_signature_verified(self, processor):
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        event = processor.process("modulr", body, {"X-Mod-Signature": sig})
        assert event.signature_valid is True
        # No handlers registered → VERIFIED (handlers set PROCESSED)
        assert event.status == WebhookStatus.VERIFIED

    def test_invalid_signature_rejected(self, processor):
        body = _modulr_body()
        event = processor.process("modulr", body, {"X-Mod-Signature": "bad-sig"})
        assert event.signature_valid is False
        assert event.status == WebhookStatus.SIGNATURE_FAILED

    def test_event_type_extracted(self, processor):
        body = _modulr_body("PAYMENT_FAILED")
        sig = _modulr_sig(body, MODULR_SECRET)
        event = processor.process("modulr", body, {"X-Mod-Signature": sig})
        assert event.event_type == "PAYMENT_FAILED"

    def test_provider_set_correctly(self, processor):
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        event = processor.process("modulr", body, {"X-Mod-Signature": sig})
        assert event.provider == WebhookProvider.MODULR


# ── Sumsub webhooks ────────────────────────────────────────────────────────────

class TestSumsubWebhook:
    def test_valid_signature_verified(self, processor):
        body = _sumsub_body()
        sig = _sumsub_sig(body, SUMSUB_SECRET)
        event = processor.process("sumsub", body, {"X-Payload-Digest": sig})
        assert event.signature_valid is True

    def test_event_type_extracted(self, processor):
        body = _sumsub_body("applicantPending")
        sig = _sumsub_sig(body, SUMSUB_SECRET)
        event = processor.process("sumsub", body, {"X-Payload-Digest": sig})
        assert event.event_type == "applicantPending"


# ── n8n internal webhooks ──────────────────────────────────────────────────────

class TestN8nWebhook:
    def test_n8n_trusted_without_sig(self, processor):
        body = json.dumps({"event": "sla_breach", "complaint_id": "c-001"}).encode()
        event = processor.process("n8n", body, {})
        assert event.signature_valid is True
        assert event.event_type == "sla_breach"


# ── Unknown provider ───────────────────────────────────────────────────────────

class TestUnknownProvider:
    def test_unknown_provider_rejected(self, processor):
        body = b'{"event": "test"}'
        event = processor.process("unknown-provider", body, {})
        assert event.signature_valid is False
        assert event.provider == WebhookProvider.UNKNOWN


# ── Audit trail (I-24) ─────────────────────────────────────────────────────────

class TestAuditTrail:
    def test_all_webhooks_stored(self, processor):
        # Even failed signature → stored
        body = _modulr_body()
        processor.process("modulr", body, {"X-Mod-Signature": "wrong"})
        audit = processor._audit
        assert len(audit.all_events()) == 1

    def test_webhook_id_unique(self, processor):
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        e1 = processor.process("modulr", body, {"X-Mod-Signature": sig})
        e2 = processor.process("modulr", body, {"X-Mod-Signature": sig})
        assert e1.webhook_id != e2.webhook_id

    def test_audit_record_serializable(self, processor):
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        event = processor.process("modulr", body, {"X-Mod-Signature": sig})
        record = event.to_audit_record()
        assert "webhook_id" in record
        assert "provider" in record
        assert "event_type" in record
        assert isinstance(record["signature_valid"], int)

    def test_by_provider_filter(self, processor):
        # Modulr webhook
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        processor.process("modulr", body, {"X-Mod-Signature": sig})
        # Sumsub webhook
        body2 = _sumsub_body()
        sig2 = _sumsub_sig(body2, SUMSUB_SECRET)
        processor.process("sumsub", body2, {"X-Payload-Digest": sig2})

        modulr_events = processor._audit.by_provider(WebhookProvider.MODULR)
        assert len(modulr_events) == 1


# ── Handlers ───────────────────────────────────────────────────────────────────

class TestHandlers:
    def test_handler_called_on_valid(self, processor):
        received = []
        processor.register_handler(WebhookProvider.MODULR, lambda ev: received.append(ev))
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        processor.process("modulr", body, {"X-Mod-Signature": sig})
        assert len(received) == 1

    def test_handler_not_called_on_invalid_sig(self, processor):
        received = []
        processor.register_handler(WebhookProvider.MODULR, lambda ev: received.append(ev))
        body = _modulr_body()
        processor.process("modulr", body, {"X-Mod-Signature": "bad"})
        assert len(received) == 0

    def test_failing_handler_recorded(self, processor):
        def bad_handler(ev):
            raise RuntimeError("handler error")
        processor.register_handler(WebhookProvider.MODULR, bad_handler)
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        event = processor.process("modulr", body, {"X-Mod-Signature": sig})
        assert event.status == WebhookStatus.FAILED
        assert event.error == "handler error"


# ── Replay ────────────────────────────────────────────────────────────────────

class TestReplay:
    def test_replay_returns_event(self, processor):
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        original = processor.process("modulr", body, {"X-Mod-Signature": sig})
        replayed = processor.replay(original.webhook_id)
        assert replayed is not None
        assert replayed.status == WebhookStatus.REPLAYED

    def test_replay_nonexistent_returns_none(self, processor):
        assert processor.replay("does-not-exist") is None

    def test_replay_calls_handler(self, processor):
        received = []
        processor.register_handler(WebhookProvider.MODULR, lambda ev: received.append(ev))
        body = _modulr_body()
        sig = _modulr_sig(body, MODULR_SECRET)
        original = processor.process("modulr", body, {"X-Mod-Signature": sig})
        received.clear()  # reset after initial process
        processor.replay(original.webhook_id)
        assert len(received) == 1
