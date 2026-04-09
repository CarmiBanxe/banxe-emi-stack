"""
api/routers/sanctions_rescreen.py — High-risk sanctions re-screen endpoint
IL-068 | AML/Compliance block | banxe-emi-stack

POST /compliance/sanctions/rescreen/high-risk — enqueue batch re-screen

Called by:
  - n8n watchman_rescreen_high_risk workflow (after Watchman list update)
  - banxe_aml_orchestrator (manual trigger)

Pipeline:
  1. Validate X-Internal-Token against env INTERNAL_API_TOKEN
  2. Enqueue job to Redis list banxe:sanctions:rescreen:high_risk
  3. Worker reads queue → calls sanctions_check_core / yente_adapter_agent per customer
  4. HITL gates (Sanctions_reversal, PEP_onboarding) enforced per-customer by OrgRoleChecker
  5. Return 202 Accepted with job_id

FCA basis: MLR 2017 Reg.28(1) — screening must reflect current lists.
           JMLSG 3.10 — MLRO oversight of re-screening procedures.
           I-24: job audit log, append-only.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger("banxe.aml.sanctions_rescreen")

router = APIRouter(prefix="/compliance/sanctions", tags=["Sanctions / AML"])

REDIS_QUEUE_KEY = "banxe:sanctions:rescreen:high_risk"

# In-memory job log for tests (prod: ClickHouse / Redis audit stream)
_JOB_LOG: list[dict] = []  # type: ignore[type-arg]


def get_job_log() -> list[dict]:  # type: ignore[type-arg]
    return list(_JOB_LOG)


def clear_job_log() -> None:
    _JOB_LOG.clear()


# ── Models ────────────────────────────────────────────────────────────────────


class HighRiskRescreenRequest(BaseModel):
    reason: str
    list_name: str | None = None
    as_of: datetime | None = None


class HighRiskRescreenEnqueued(BaseModel):
    job_id: str
    queued_at: datetime
    queue: str
    redis_available: bool


# ── Redis helper (optional — falls back to in-memory log) ────────────────────


def _enqueue_redis(job_id: str, job_payload: dict) -> bool:  # type: ignore[type-arg]
    """
    Enqueue re-screen job to Redis list.
    Falls back gracefully if redis is unavailable (e.g. unit tests).
    """
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return False
    try:
        import redis as redis_lib

        r = redis_lib.from_url(redis_url, decode_responses=True)
        r.lpush(REDIS_QUEUE_KEY, json.dumps(job_payload))
        logger.info("Re-screen job %s enqueued to Redis", job_id[:8])
        return True
    except Exception as exc:
        logger.warning("Redis unavailable for re-screen job: %s", type(exc).__name__)
        return False


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/rescreen/high-risk",
    response_model=HighRiskRescreenEnqueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue high-risk sanctions re-screen (triggered after Watchman list update)",
)
def rescreen_high_risk(
    payload: HighRiskRescreenRequest,
    x_internal_token: str = Header(default=""),
) -> HighRiskRescreenEnqueued:
    """
    Enqueues a batch re-screen of high-risk / PEP-potential customers.

    Worker picks up from banxe:sanctions:rescreen:high_risk Redis list,
    calls sanctions_check_core / yente_adapter_agent per customer,
    and routes any new hits through HITL gates (OrgRoleChecker).

    Security: X-Internal-Token required (internal service-to-service only).
    """
    expected_token = os.environ.get("INTERNAL_API_TOKEN", "")
    if expected_token and x_internal_token != expected_token:
        logger.warning(
            "sanctions_rescreen: invalid token (reason=%s list=%s)",
            payload.reason,
            payload.list_name or "N/A",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )

    now = datetime.now(UTC)
    job_id = str(uuid.uuid4())

    job_payload = {
        "job_id": job_id,
        "type": "high_risk_rescreen",
        "reason": payload.reason,
        "list_name": payload.list_name,
        "as_of": (payload.as_of or now).isoformat(),
        "queued_at": now.isoformat(),
    }

    redis_ok = _enqueue_redis(job_id, job_payload)

    # Always audit-log locally (I-24)
    _JOB_LOG.append(job_payload)

    logger.info(
        "Re-screen job enqueued: job_id=%s reason=%s list=%s redis=%s",
        job_id[:8],
        payload.reason,
        payload.list_name or "N/A",
        redis_ok,
    )

    return HighRiskRescreenEnqueued(
        job_id=job_id,
        queued_at=now,
        queue=REDIS_QUEUE_KEY,
        redis_available=redis_ok,
    )
