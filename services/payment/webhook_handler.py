"""
webhook_handler.py — FastAPI webhook receiver for Modulr payment events
Block C-fps + C-sepa, IL-014
FCA PSR / PSD2 | banxe-emi-stack

OVERVIEW
--------
Modulr fires webhooks on payment status changes:
  - payment.processing → payment.completed
  - payment.processing → payment.failed
  - payment.completed  → payment.returned

This FastAPI router:
  1. Verifies HMAC-SHA256 signature (rejects unsigned requests)
  2. Parses payload → PaymentStatusUpdate
  3. Updates ClickHouse banxe.payment_events (append-only, I-24)
  4. Fires n8n alert for FAILED / RETURNED events

Mount this router in the main FastAPI app (or as standalone service on :8889).

Modulr webhook registration:
  URL: https://your-domain/webhooks/modulr/payment
  Events: payment.processed, payment.failed, payment.returned
  Secret: MODULR_API_SECRET (same as API secret)

Security:
  - All requests without valid HMAC-SHA256 → 401 REJECTED + logged
  - Request body is read raw BEFORE JSON parsing (signature is over raw bytes)
  - IP allowlist: Modulr IP ranges (configure in nginx / firewall)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

MODULR_API_SECRET = os.environ.get("MODULR_API_SECRET", "")
VERIFY_SIGNATURES = os.environ.get("MODULR_VERIFY_SIGNATURES", "true").lower() == "true"


def create_webhook_router(ch_client=None):
    """
    Create and return the FastAPI router for Modulr webhooks.

    Import FastAPI lazily so this file can be imported in test environments
    without FastAPI installed.

    Args:
        ch_client: ClickHouseClientProtocol for audit writes.
                   If None, builds ClickHouseReconClient.
    """
    try:
        from fastapi import APIRouter, Header, HTTPException, Request, status
        from fastapi.responses import JSONResponse
    except ImportError:
        raise RuntimeError("fastapi is required: pip install fastapi")

    if ch_client is None:
        from services.recon.clickhouse_client import ClickHouseReconClient

        ch_client = ClickHouseReconClient()

    from services.payment.modulr_client import ModulrPaymentAdapter

    adapter = ModulrPaymentAdapter()

    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    @router.post("/modulr/payment", status_code=status.HTTP_200_OK)
    async def modulr_payment_webhook(
        request: Request,
        x_mod_signature: str | None = Header(None, alias="X-Mod-Signature"),
    ):
        """
        Receive Modulr payment status update webhook.

        Modulr sends events when payments move through their lifecycle:
          PROCESSING → PROCESSED (completed, irrevocable)
          PROCESSING → FAILED
          PROCESSED  → RETURNED

        FCA requirement: every status change MUST be recorded in audit trail.
        """
        raw_body = await request.body()

        # ── 1. Verify signature ───────────────────────────────────────────────
        if VERIFY_SIGNATURES:
            if not x_mod_signature:
                logger.warning("Modulr webhook: missing X-Mod-Signature header — rejected")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing webhook signature",
                )
            if not adapter.verify_webhook_signature(raw_body, x_mod_signature):
                logger.warning("Modulr webhook: invalid HMAC signature — rejected")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )

        # ── 2. Parse payload ──────────────────────────────────────────────────
        try:
            import json

            payload = json.loads(raw_body)
        except Exception as exc:
            logger.error("Modulr webhook: JSON parse failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        event_type = payload.get("type", "")
        logger.info("Modulr webhook received: type=%s id=%s", event_type, payload.get("id", ""))

        # ── 3. Parse status update ────────────────────────────────────────────
        try:
            update = ModulrPaymentAdapter.parse_webhook_event(payload)
        except Exception as exc:
            logger.error("Modulr webhook: parse_webhook_event failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Could not parse webhook payload: {exc}",
            )

        # ── 4. Write to ClickHouse (append-only audit, I-24) ─────────────────
        try:
            ch_client.execute(
                """
                INSERT INTO banxe.payment_events
                (idempotency_key, provider_payment_id, rail, direction,
                 amount, currency, status, submitted_at)
                VALUES
                """,
                {
                    "idempotency_key": update.idempotency_key or "",
                    "provider_payment_id": update.provider_payment_id,
                    "rail": update.rail.value,
                    "direction": "OUTBOUND",
                    "amount": str(update.amount),
                    "currency": update.currency,
                    "status": update.new_status.value,
                    "error_code": "",
                    "debtor_name": "",
                    "creditor_name": "",
                    "reference": "",
                    "submitted_at": update.occurred_at.isoformat(),
                },
            )
        except Exception as exc:
            # Never let audit failure block the 200 OK to Modulr
            # (Modulr will retry on non-200, causing duplicate processing)
            logger.error("ClickHouse audit write failed in webhook: %s", exc)

        # ── 5. Alert on FAILED / RETURNED ────────────────────────────────────
        from services.payment.payment_port import PaymentStatus

        if update.new_status in (PaymentStatus.FAILED, PaymentStatus.RETURNED):
            logger.warning(
                "Payment %s: %s (id=%s amount=%s%s)",
                update.new_status.value,
                update.idempotency_key,
                update.provider_payment_id,
                update.amount,
                update.currency,
            )
            _fire_alert(update)

        return JSONResponse({"status": "accepted", "id": update.provider_payment_id})

    @router.get("/modulr/health")
    async def webhook_health():
        """Liveness probe for webhook service."""
        return {"status": "ok", "service": "modulr-webhook", "verify_signatures": VERIFY_SIGNATURES}

    return router


def _fire_alert(update) -> None:
    """Fire n8n alert for failed/returned payments."""
    n8n_url = os.environ.get("N8N_WEBHOOK_URL", "")
    if not n8n_url:
        return
    try:
        import httpx

        httpx.post(
            n8n_url,
            json={
                "event": f"payment_{update.new_status.value.lower()}",
                "provider_payment_id": update.provider_payment_id,
                "rail": update.rail.value,
                "amount": str(update.amount),
                "currency": update.currency,
                "occurred_at": update.occurred_at.isoformat(),
            },
            timeout=5.0,
        )
    except Exception as exc:
        logger.warning("n8n alert failed in webhook handler: %s", exc)
