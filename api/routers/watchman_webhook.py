"""
api/routers/watchman_webhook.py — Watchman list-update webhook handler
IL-068 | AML/Compliance block | banxe-emi-stack

POST /webhooks/watchman — receive Watchman list_updated / search_notification events

Pipeline:
  1. Validate X-Watchman-Secret header against env WATCHMAN_WEBHOOK_SECRET
  2. Audit-log raw event to InMemoryWebhookAuditStore (prod: ClickHouseWebhookAuditStore)
  3. Trigger n8n workflow watchman_list_update (fire-and-forget, best-effort)
  4. Return 202 Accepted immediately

FCA basis: MLR 2017 Reg.28(1) — sanctions screening must reflect current lists.
           I-24: all webhook events logged (append-only audit trail).
           I-09: no PII in server logs — only event_type and list_name.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from services.webhooks.webhook_router import (
    InMemoryWebhookAuditStore,
    WebhookProcessor,
)

logger = logging.getLogger("banxe.aml.watchman_webhook")

router = APIRouter(prefix="/webhooks", tags=["Watchman / AML"])

# Shared processor instance (single webhook provider: watchman)
_processor = WebhookProcessor(
    secrets={"watchman": os.environ.get("WATCHMAN_WEBHOOK_SECRET", "")},
    audit_store=InMemoryWebhookAuditStore(),
)


# ── Request / Response models ─────────────────────────────────────────────────


class WatchmanWebhookPayload(BaseModel):
    type: Literal["list_updated", "search_notification", "health"]
    list: str | None = None
    timestamp: datetime
    details: dict | None = None  # type: ignore[type-arg]


class WatchmanWebhookResponse(BaseModel):
    status: str
    event_type: str
    list_name: str | None = None
    n8n_triggered: bool


# ── n8n trigger (fire-and-forget) ─────────────────────────────────────────────


def _trigger_n8n_watchman_update(payload: WatchmanWebhookPayload) -> bool:
    """
    POST to n8n webhook for watchman_list_update workflow.
    Best-effort: failures are logged but do not block the 202 response.
    N8N_INTERNAL_URL defaults to http://localhost:5678 (GMKtec n8n).
    """
    n8n_url = os.environ.get("N8N_INTERNAL_URL", "http://localhost:5678")
    webhook_path = "/webhook/watchman-list-update"
    try:
        import httpx

        body = {
            "event_type": payload.type,
            "list_name": payload.list,
            "timestamp": payload.timestamp.isoformat(),
            "details": payload.details or {},
        }
        resp = httpx.post(
            f"{n8n_url}{webhook_path}",
            json=body,
            timeout=3.0,
            headers={"X-Internal-Token": os.environ.get("INTERNAL_API_TOKEN", "")},
        )
        if resp.is_error:
            logger.warning("n8n watchman_list_update returned %s", resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.warning("n8n watchman_list_update trigger failed: %s", type(exc).__name__)
        return False


# ── Webhook endpoint ──────────────────────────────────────────────────────────


@router.post(
    "/watchman",
    response_model=WatchmanWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive Watchman list-update webhook (AML sanctions screening)",
)
def receive_watchman_webhook(
    payload: WatchmanWebhookPayload,
    request: Request,
    x_watchman_secret: str = Header(default=""),
) -> WatchmanWebhookResponse:
    """
    Inbound webhook from Moov Watchman (via Banxe Screener).
    Validates shared secret, logs event (I-24), triggers n8n workflow.

    Watchman sends this on:
    - list_updated: OFAC/HMT/EU/UN list refresh
    - search_notification: async search result available
    - health: liveness ping from Watchman admin

    MLRO and Head of Financial Crime are notified via n8n → /internal/notifications/mlro.
    """
    expected_secret = os.environ.get("WATCHMAN_WEBHOOK_SECRET", "")
    if expected_secret and x_watchman_secret != expected_secret:
        logger.warning(
            "Watchman webhook: invalid secret from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    # Audit log via WebhookProcessor (I-24: append-only)
    _processor.process(
        provider="watchman",
        body=request.state._state.get("body", b""),
        headers=dict(request.headers),
    )

    # For health pings — acknowledge without triggering n8n
    if payload.type == "health":
        logger.info("Watchman health ping received")
        return WatchmanWebhookResponse(
            status="accepted",
            event_type="health",
            n8n_triggered=False,
        )

    logger.info(
        "Watchman webhook: type=%s list=%s",
        payload.type,
        payload.list or "N/A",
    )

    n8n_ok = _trigger_n8n_watchman_update(payload)

    return WatchmanWebhookResponse(
        status="accepted",
        event_type=payload.type,
        list_name=payload.list,
        n8n_triggered=n8n_ok,
    )
