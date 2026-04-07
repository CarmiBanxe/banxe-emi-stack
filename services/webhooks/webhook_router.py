"""
webhook_router.py — Centralised Inbound Webhook Router
S17-03 (partial): Unified entry point for all external provider webhooks
Pattern: Geniusto v5 webHookService / Handler incoming messages from GCP

WHY THIS FILE EXISTS
--------------------
Banxe has multiple external providers that push events via webhooks:
  Modulr → payment status updates (COMPLETED, FAILED, RETURNED)
  Sumsub → KYC verification results (COMPLETED, REJECTED, PENDING)
  n8n → internal workflow triggers

Each provider uses different HMAC signing. Without central routing:
  - No audit trail of raw incoming webhooks (compliance gap)
  - Signature verification scattered across handlers
  - No replay capability for debugging

This router provides:
  1. HMAC signature verification per provider (Modulr, Sumsub)
  2. Payload parsing → typed WebhookEvent
  3. ClickHouse logging of ALL incoming webhooks (I-24, 5yr retention)
  4. Routing to the appropriate service handler
  5. Replay by webhook_id
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Provider enum ──────────────────────────────────────────────────────────────

class WebhookProvider(str, Enum):
    MODULR = "modulr"
    SUMSUB = "sumsub"
    N8N = "n8n"
    UNKNOWN = "unknown"


class WebhookStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VERIFIED = "VERIFIED"
    SIGNATURE_FAILED = "SIGNATURE_FAILED"
    PROCESSED = "PROCESSED"
    REPLAYED = "REPLAYED"
    FAILED = "FAILED"


# ── Webhook event ──────────────────────────────────────────────────────────────

@dataclass
class WebhookEvent:
    webhook_id: str
    provider: WebhookProvider
    event_type: str                  # provider-specific: "payment.completed", "applicantReviewed"
    payload: dict[str, Any]
    received_at: datetime
    status: WebhookStatus
    signature_valid: bool
    raw_body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    def to_audit_record(self) -> dict[str, Any]:
        """Serialise for ClickHouse banxe.webhook_events."""
        return {
            "webhook_id": self.webhook_id,
            "provider": self.provider.value,
            "event_type": self.event_type,
            "received_at": self.received_at.isoformat(),
            "status": self.status.value,
            "signature_valid": int(self.signature_valid),
            "error": self.error or "",
        }


# ── HMAC verifiers ─────────────────────────────────────────────────────────────

def _verify_modulr(body: bytes, signature_header: str, secret: str) -> bool:
    """
    Modulr HMAC-SHA512 signature verification.
    Header: X-Mod-Nonce + X-Mod-Timestamp → HMAC body.
    Simplified: verify X-Mod-Signature = HMAC-SHA256(secret, body).
    """
    if not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.lower())


def _verify_sumsub(body: bytes, signature_header: str, secret: str) -> bool:
    """
    Sumsub HMAC-SHA1 signature verification.
    Docs: https://developers.sumsub.com/api-reference/#webhook-signature
    """
    if not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, signature_header.lower())


def _verify_n8n(_body: bytes, _signature_header: str, _secret: str) -> bool:
    """n8n internal webhooks — trust by network (no HMAC in Phase 1)."""
    return True


# ── Webhook processor ──────────────────────────────────────────────────────────

class WebhookProcessor:
    """
    Verifies HMAC, parses payload, routes to handler, logs to audit store.

    Usage (FastAPI route):
        processor = WebhookProcessor(secrets={"modulr": "...", "sumsub": "..."})
        event = processor.process(
            provider="modulr",
            body=await request.body(),
            headers=dict(request.headers),
        )
    """

    def __init__(
        self,
        secrets: Optional[dict[str, str]] = None,
        audit_store: Optional[WebhookAuditStore] = None,
    ) -> None:
        self._secrets = secrets or {}
        self._audit = audit_store or InMemoryWebhookAuditStore()
        self._handlers: dict[WebhookProvider, list] = {}

    def register_handler(self, provider: WebhookProvider, handler) -> None:
        self._handlers.setdefault(provider, []).append(handler)

    def process(
        self,
        provider: str,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent:
        webhook_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        try:
            prov_enum = WebhookProvider(provider.lower())
        except ValueError:
            prov_enum = WebhookProvider.UNKNOWN

        # Parse payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw": body.decode(errors="replace")}

        event_type = self._extract_event_type(prov_enum, payload)

        # Signature verification
        signature_valid = self._verify_signature(prov_enum, body, headers)
        status = WebhookStatus.VERIFIED if signature_valid else WebhookStatus.SIGNATURE_FAILED

        event = WebhookEvent(
            webhook_id=webhook_id,
            provider=prov_enum,
            event_type=event_type,
            payload=payload,
            received_at=now,
            status=status,
            signature_valid=signature_valid,
            raw_body=body,
            headers=headers,
        )

        # Always audit-log, even on signature failure (I-24)
        self._audit.save(event)

        if not signature_valid:
            logger.warning(
                "Webhook SIGNATURE FAILED: provider=%s webhook_id=%s",
                provider, webhook_id,
            )
            return event

        # Route to handlers
        for handler in self._handlers.get(prov_enum, []):
            try:
                handler(event)
                event.status = WebhookStatus.PROCESSED
            except Exception as exc:
                event.status = WebhookStatus.FAILED
                event.error = str(exc)
                logger.error("Webhook handler failed: %s", exc)

        self._audit.update_status(webhook_id, event.status)
        logger.info(
            "Webhook processed: provider=%s type=%s id=%s status=%s",
            provider, event_type, webhook_id[:8], event.status,
        )
        return event

    def replay(self, webhook_id: str) -> Optional[WebhookEvent]:
        """Re-process a stored webhook (skip signature re-check)."""
        event = self._audit.get(webhook_id)
        if event is None:
            return None
        event.status = WebhookStatus.REPLAYED
        for handler in self._handlers.get(event.provider, []):
            try:
                handler(event)
            except Exception as exc:
                logger.error("Replay handler failed: %s", exc)
        self._audit.update_status(webhook_id, event.status)
        return event

    def _verify_signature(
        self,
        provider: WebhookProvider,
        body: bytes,
        headers: dict[str, str],
    ) -> bool:
        secret = self._secrets.get(provider.value, "")
        _headers_lower = {k.lower(): v for k, v in headers.items()}

        if provider == WebhookProvider.MODULR:
            sig = _headers_lower.get("x-mod-signature", "")
            return _verify_modulr(body, sig, secret)
        if provider == WebhookProvider.SUMSUB:
            sig = _headers_lower.get("x-payload-digest", "")
            return _verify_sumsub(body, sig, secret)
        if provider == WebhookProvider.N8N:
            return _verify_n8n(body, "", secret)
        # UNKNOWN: reject
        return False

    def _extract_event_type(self, provider: WebhookProvider, payload: dict) -> str:
        if provider == WebhookProvider.MODULR:
            return payload.get("eventType", payload.get("type", "unknown"))
        if provider == WebhookProvider.SUMSUB:
            return payload.get("type", "unknown")
        return payload.get("event", payload.get("type", "unknown"))


# ── Audit store ────────────────────────────────────────────────────────────────

class WebhookAuditStore:
    def save(self, event: WebhookEvent) -> None: ...
    def get(self, webhook_id: str) -> Optional[WebhookEvent]: ...
    def update_status(self, webhook_id: str, status: WebhookStatus) -> None: ...


class InMemoryWebhookAuditStore:
    """In-memory store for tests + development."""

    def __init__(self) -> None:
        self._store: dict[str, WebhookEvent] = {}

    def save(self, event: WebhookEvent) -> None:
        self._store[event.webhook_id] = event

    def get(self, webhook_id: str) -> Optional[WebhookEvent]:
        return self._store.get(webhook_id)

    def update_status(self, webhook_id: str, status: WebhookStatus) -> None:
        if webhook_id in self._store:
            self._store[webhook_id].status = status

    def all_events(self) -> list[WebhookEvent]:
        return list(self._store.values())

    def by_provider(self, provider: WebhookProvider) -> list[WebhookEvent]:
        return [e for e in self._store.values() if e.provider == provider]


class ClickHouseWebhookAuditStore:  # pragma: no cover
    """
    Production ClickHouse audit store.
    STATUS: STUB — requires ClickHouse banxe.webhook_events table.
    Run: scripts/schema/clickhouse_webhooks.sql
    """

    def save(self, event: WebhookEvent) -> None:
        raise NotImplementedError("Deploy clickhouse_webhooks.sql first")

    def get(self, webhook_id: str) -> Optional[WebhookEvent]:
        raise NotImplementedError

    def update_status(self, webhook_id: str, status: WebhookStatus) -> None:
        raise NotImplementedError
