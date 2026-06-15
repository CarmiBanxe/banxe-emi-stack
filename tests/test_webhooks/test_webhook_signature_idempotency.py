"""G-KYC-04: Webhook signature verification + idempotency-key coverage.

6 tests against SumSub inbound webhook path (services.webhooks.webhook_router).

Spec/HTTP mapping — the WebhookProcessor is a sync library returning a
WebhookEvent (not a FastAPI route), so we map the spec's HTTP semantics to
the equivalent WebhookStatus / signature_valid signals:
  - "202 Accepted"          ≈ signature_valid=True  + status ∈ {VERIFIED, PROCESSED}
  - "401/403 Rejected"      ≈ signature_valid=False + status == SIGNATURE_FAILED
  - "5xx → DLQ"             ≈ status == FAILED + error captured + event retained in audit
                               store (replay-eligible per WebhookProcessor.replay)
  - Idempotency             ≈ handler-side dedup keyed on payload's idempotency key
                               (applicantId + type). Router accepts everything; the
                               consumer enforces idempotent processing.

Per ADR-034 Webhook Reliability KYC + FCA MLR 2017 Reg.28.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

from services.webhooks.webhook_router import (
    InMemoryWebhookAuditStore,
    WebhookEvent,
    WebhookProcessor,
    WebhookProvider,
    WebhookStatus,
)

SUMSUB_SECRET = "test-sumsub-secret"


def _sumsub_body(
    event_type: str = "applicantReviewed",
    applicant_id: str = "app-001",
    review_status: str = "completed",
) -> bytes:
    return json.dumps(
        {
            "type": event_type,
            "applicantId": applicant_id,
            "reviewStatus": review_status,
        }
    ).encode()


def _sumsub_sig(body: bytes, secret: str = SUMSUB_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()


@pytest.fixture
def processor() -> WebhookProcessor:
    return WebhookProcessor(
        secrets={"sumsub": SUMSUB_SECRET},
        audit_store=InMemoryWebhookAuditStore(),
    )


def test_valid_signature_accepted(processor: WebhookProcessor) -> None:
    body = _sumsub_body()
    headers = {"X-Payload-Digest": _sumsub_sig(body)}

    event = processor.process("sumsub", body, headers)

    assert event.signature_valid is True
    assert event.status == WebhookStatus.VERIFIED
    assert event.provider == WebhookProvider.SUMSUB


def test_invalid_signature_rejected(processor: WebhookProcessor) -> None:
    body = _sumsub_body()
    headers = {"X-Payload-Digest": "deadbeef" * 5}

    event = processor.process("sumsub", body, headers)

    assert event.signature_valid is False
    assert event.status == WebhookStatus.SIGNATURE_FAILED


def test_missing_signature_rejected(processor: WebhookProcessor) -> None:
    body = _sumsub_body()

    event = processor.process("sumsub", body, headers={})

    assert event.signature_valid is False
    assert event.status == WebhookStatus.SIGNATURE_FAILED


def test_replay_attack_idempotency(processor: WebhookProcessor) -> None:
    processed_keys: list[tuple[str, str]] = []

    def idempotent_handler(event: WebhookEvent) -> None:
        key = (event.payload["applicantId"], event.event_type)
        if key in processed_keys:
            return
        processed_keys.append(key)

    processor.register_handler(WebhookProvider.SUMSUB, idempotent_handler)

    body = _sumsub_body(applicant_id="app-replay-001")
    headers = {"X-Payload-Digest": _sumsub_sig(body)}

    first = processor.process("sumsub", body, headers)
    second = processor.process("sumsub", body, headers)

    assert first.signature_valid is True
    assert second.signature_valid is True
    assert first.status == WebhookStatus.PROCESSED
    assert second.status == WebhookStatus.PROCESSED
    assert processed_keys == [("app-replay-001", "applicantReviewed")]


def test_out_of_order_delivery(processor: WebhookProcessor) -> None:
    seen: list[str] = []

    def tolerant_handler(event: WebhookEvent) -> None:
        seen.append(event.payload["reviewStatus"])

    processor.register_handler(WebhookProvider.SUMSUB, tolerant_handler)

    rejected_body = _sumsub_body(applicant_id="app-ooo", review_status="rejected")
    completed_body = _sumsub_body(applicant_id="app-ooo", review_status="completed")

    rejected_event = processor.process(
        "sumsub", rejected_body, {"X-Payload-Digest": _sumsub_sig(rejected_body)}
    )
    completed_event = processor.process(
        "sumsub", completed_body, {"X-Payload-Digest": _sumsub_sig(completed_body)}
    )

    assert rejected_event.status == WebhookStatus.PROCESSED
    assert completed_event.status == WebhookStatus.PROCESSED
    assert seen == ["rejected", "completed"]


def test_5xx_response_path(processor: WebhookProcessor) -> None:
    def failing_handler(_event: WebhookEvent) -> None:
        raise RuntimeError("downstream KYC service returned 503")

    processor.register_handler(WebhookProvider.SUMSUB, failing_handler)
    audit: Any = processor._audit  # InMemoryWebhookAuditStore

    body = _sumsub_body(applicant_id="app-5xx")
    headers = {"X-Payload-Digest": _sumsub_sig(body)}

    event = processor.process("sumsub", body, headers)

    assert event.status == WebhookStatus.FAILED
    assert event.error is not None
    assert "503" in event.error

    stored = audit.get(event.webhook_id)
    assert stored is not None, (
        "FAILED webhook must remain in audit store (DLQ-replayable, not silently lost)"
    )
    assert stored.status == WebhookStatus.FAILED

    replayed = processor.replay(event.webhook_id)
    assert replayed is not None
    assert replayed.status == WebhookStatus.REPLAYED
