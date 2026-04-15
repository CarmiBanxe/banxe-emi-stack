"""
tests/test_webhook_audit.py — InMemoryWebhookAuditStore + WebhookProcessor tests
S15-FIX-2 | FCA I-24 (audit trail) | banxe-emi-stack

12 tests: CRUD, pagination, provider filtering, signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from services.webhooks.webhook_router import (
    InMemoryWebhookAuditStore,
    WebhookEvent,
    WebhookProcessor,
    WebhookProvider,
    WebhookStatus,
)


@pytest.fixture
def store() -> InMemoryWebhookAuditStore:
    return InMemoryWebhookAuditStore()


@pytest.fixture
def processor() -> WebhookProcessor:
    return WebhookProcessor(secrets={})


def _make_event(
    provider: WebhookProvider = WebhookProvider.N8N,
    event_type: str = "payment.completed",
) -> WebhookEvent:
    from datetime import UTC, datetime

    return WebhookEvent(
        webhook_id=f"wh-{event_type}-{provider.value}",
        provider=provider,
        event_type=event_type,
        payload={"type": event_type},
        received_at=datetime.now(UTC),
        status=WebhookStatus.RECEIVED,
        signature_valid=True,
        raw_body=json.dumps({"type": event_type}).encode(),
    )


class TestInMemoryWebhookAuditStore:
    def test_save_and_get(self, store):
        ev = _make_event()
        store.save(ev)
        retrieved = store.get(ev.webhook_id)
        assert retrieved is not None
        assert retrieved.webhook_id == ev.webhook_id

    def test_get_nonexistent_returns_none(self, store):
        assert store.get("does-not-exist") is None

    def test_update_status(self, store):
        ev = _make_event()
        store.save(ev)
        store.update_status(ev.webhook_id, WebhookStatus.PROCESSED)
        assert store.get(ev.webhook_id).status == WebhookStatus.PROCESSED

    def test_update_status_nonexistent_no_error(self, store):
        # Should not raise
        store.update_status("ghost", WebhookStatus.FAILED)

    def test_all_events_empty(self, store):
        assert store.all_events() == []

    def test_all_events_returns_all(self, store):
        for i in range(3):
            ev = _make_event(event_type=f"event-{i}")
            ev.webhook_id = f"wh-{i}"
            store.save(ev)
        assert len(store.all_events()) == 3

    def test_by_provider_filter(self, store):
        modulr_ev = _make_event(provider=WebhookProvider.MODULR, event_type="payment.done")
        n8n_ev = _make_event(provider=WebhookProvider.N8N, event_type="workflow.run")
        store.save(modulr_ev)
        store.save(n8n_ev)
        modulr_events = store.by_provider(WebhookProvider.MODULR)
        assert len(modulr_events) == 1
        assert modulr_events[0].provider == WebhookProvider.MODULR

    def test_by_provider_empty_result(self, store):
        ev = _make_event(provider=WebhookProvider.N8N)
        store.save(ev)
        sumsub_events = store.by_provider(WebhookProvider.SUMSUB)
        assert sumsub_events == []


class TestWebhookProcessor:
    def test_n8n_webhook_processed(self, processor):
        body = json.dumps({"event": "workflow.trigger", "data": {}}).encode()
        event = processor.process("n8n", body, {})
        assert event.provider == WebhookProvider.N8N
        assert event.signature_valid is True

    def test_unknown_provider_signature_fails(self, processor):
        body = json.dumps({"type": "unknown_event"}).encode()
        event = processor.process("unknown_provider", body, {})
        assert event.signature_valid is False
        assert event.status == WebhookStatus.SIGNATURE_FAILED

    def test_event_audited_even_on_signature_failure(self, processor):
        body = json.dumps({"type": "suspicious"}).encode()
        event = processor.process("modulr", body, {"x-mod-signature": "bad"})
        # Audit store should have the event despite signature failure
        stored = processor._audit.get(event.webhook_id)
        assert stored is not None

    def test_modulr_correct_signature(self):
        secret = "test-secret-modulr"
        body = json.dumps({"eventType": "PAYMENT_COMPLETED"}).encode()
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        proc = WebhookProcessor(secrets={"modulr": secret})
        event = proc.process("modulr", body, {"x-mod-signature": sig})
        assert event.signature_valid is True
        assert event.event_type == "PAYMENT_COMPLETED"
