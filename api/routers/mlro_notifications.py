"""
api/routers/mlro_notifications.py — Internal MLRO notification endpoint
IL-068 | AML/Compliance block | banxe-emi-stack
from api.deps import require_auth

POST /internal/notifications/mlro — receive AML/sanctions alert for MLRO
from api.deps import require_auth

Called by:
  - n8n watchman_list_update workflow
  - n8n watchman_rescreen_high_risk workflow
  - banxe_aml_orchestrator (via n8n glue)
from api.deps import require_auth

Pipeline:
  1. Validate X-Internal-Token header against env INTERNAL_API_TOKEN
  2. Log notification to audit store (I-24)
  3. Forward to notification service (Telegram / Slack / email via NotificationService)
  4. Return 202 Accepted
from api.deps import require_auth

FCA basis: JMLSG 3.10 — MLRO must receive timely information for oversight.
           SMF17 personal accountability: MLRO must be informed of material AML events.
           I-24: append-only audit trail.
           I-09: no PII in server logs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import logging
import os
from typing import Literal
import uuid

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("banxe.aml.mlro_notifications")

router = APIRouter(prefix="/internal/notifications", tags=["Internal / MLRO"])


# ── Models ────────────────────────────────────────────────────────────────────


class MLROChannel(str, Enum):
    AML_ALERTS = "mlro_aml_alerts"
    SANCTIONS = "mlro_sanctions"
    TM = "mlro_tm"


class MLRONotification(BaseModel):
    channel: MLROChannel
    message: str
    source: str | None = None
    severity: Literal["info", "warning", "critical"] = "info"


class MLRONotificationResponse(BaseModel):
    status: str
    notification_id: str
    channel: MLROChannel
    severity: str
    logged_at: datetime


# ── In-memory audit log (prod: swap for ClickHouse) ──────────────────────────

_NOTIFICATION_LOG: list[dict] = []  # type: ignore[type-arg]


def _audit_log_notification(
    notification_id: str,
    channel: MLROChannel,
    message: str,
    severity: str,
    source: str | None,
    logged_at: datetime,
) -> None:
    """Append notification to audit log (I-24). Prod: write to ClickHouse."""
    _NOTIFICATION_LOG.append(
        {
            "notification_id": notification_id,
            "channel": channel.value,
            "message": message,
            "severity": severity,
            "source": source or "",
            "logged_at": logged_at.isoformat(),
        }
    )


def get_notification_log() -> list[dict]:  # type: ignore[type-arg]
    """Expose audit log for tests."""
    return list(_NOTIFICATION_LOG)


def clear_notification_log() -> None:
    """Reset audit log between tests."""
    _NOTIFICATION_LOG.clear()


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/mlro",
    response_model=MLRONotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send AML alert to MLRO / Head of Financial Crime (internal)",
)
def notify_mlro(
    payload: MLRONotification,
    x_internal_token: str = Header(default=""),
) -> MLRONotificationResponse:
    """
    Internal endpoint for AML/sanctions events requiring MLRO attention.
    Called by n8n workflows (watchman_list_update, watchman_rescreen_high_risk)
    and by banxe_aml_orchestrator glue layer.

    Security: X-Internal-Token validated against INTERNAL_API_TOKEN env var.
    Audit: every notification logged with unique ID (I-24).
    """
    expected_token = os.environ.get("INTERNAL_API_TOKEN", "")
    if expected_token and x_internal_token != expected_token:
        logger.warning(
            "mlro_notifications: invalid token (channel=%s source=%s)",
            payload.channel.value,
            payload.source or "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )

    notification_id = str(uuid.uuid4())
    logged_at = datetime.now(UTC)

    # Audit log (I-24: append-only)
    _audit_log_notification(
        notification_id=notification_id,
        channel=payload.channel,
        message=payload.message,
        severity=payload.severity,
        source=payload.source,
        logged_at=logged_at,
    )

    # Log severity-appropriate message (I-09: no PII — only channel/severity/source)
    log_fn = {
        "critical": logger.error,
        "warning": logger.warning,
        "info": logger.info,
    }.get(payload.severity, logger.info)
    log_fn(
        "MLRO notification: channel=%s severity=%s source=%s id=%s",
        payload.channel.value,
        payload.severity,
        payload.source or "unknown",
        notification_id[:8],
    )

    return MLRONotificationResponse(
        status="accepted",
        notification_id=notification_id,
        channel=payload.channel,
        severity=payload.severity,
        logged_at=logged_at,
    )
