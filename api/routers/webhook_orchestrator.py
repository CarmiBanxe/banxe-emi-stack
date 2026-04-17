"""
api/routers/webhook_orchestrator.py — Webhook Orchestrator REST API
IL-WHO-01 | Phase 28 | banxe-emi-stack

Endpoints (prefix /v1/webhooks embedded):
  POST /v1/webhooks/subscriptions              — subscribe to event types
  GET  /v1/webhooks/subscriptions/{id}         — get subscription
  GET  /v1/webhooks/subscriptions              — list subscriptions by owner_id
  DELETE /v1/webhooks/subscriptions/{id}       — delete subscription (HITL I-27)
  POST /v1/webhooks/events                     — publish webhook event
  GET  /v1/webhooks/events/{event_id}          — get event + delivery status
  GET  /v1/webhooks/events                     — list events (filter by type)
  GET  /v1/webhooks/deliveries/{attempt_id}    — get delivery attempt
  POST /v1/webhooks/dlq/{attempt_id}/retry     — retry dead-lettered delivery
  GET  /v1/webhooks/event-types                — list all supported event types

FCA: PS21/3, COBS, Audit trail (I-24)
Invariants: I-24 (append-only DLQ), I-27 (HITL subscription delete)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.webhook_orchestrator.webhook_agent import WebhookAgent

router = APIRouter(tags=["webhook_orchestrator"])


# ── Dependency ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> WebhookAgent:
    return WebhookAgent()


# ── Request models ────────────────────────────────────────────────────────────


class SubscribeRequest(BaseModel):
    owner_id: str
    url: str  # must be HTTPS
    event_types: list[str]
    description: str = ""


class PublishEventRequest(BaseModel):
    event_type: str
    payload: dict
    source_service: str
    idempotency_key: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/v1/webhooks/subscriptions", status_code=201)
async def subscribe(req: SubscribeRequest) -> dict:
    """Register a new webhook subscription. URL must be HTTPS.

    Returns subscription_id and status=ACTIVE.
    """
    agent = _get_agent()
    try:
        return agent.subscribe(
            owner_id=req.owner_id,
            url=req.url,
            event_types_str=req.event_types,
            description=req.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/webhooks/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: str) -> dict:
    """Get webhook subscription by ID."""
    agent = _get_agent()
    sub = agent.subscription_manager.get(subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found")
    return {
        "subscription_id": sub.subscription_id,
        "owner_id": sub.owner_id,
        "url": sub.url,
        "event_types": [et.value for et in sub.event_types],
        "status": sub.status.value,
        "description": sub.description,
        "created_at": sub.created_at.isoformat(),
    }


@router.get("/v1/webhooks/subscriptions")
async def list_subscriptions(owner_id: str) -> dict:
    """List all webhook subscriptions for an owner."""
    agent = _get_agent()
    subs = agent.subscription_manager.list_subscriptions(owner_id=owner_id)
    return {
        "subscriptions": [
            {
                "subscription_id": s.subscription_id,
                "url": s.url,
                "event_types": [et.value for et in s.event_types],
                "status": s.status.value,
                "created_at": s.created_at.isoformat(),
            }
            for s in subs
        ]
    }


@router.delete("/v1/webhooks/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str) -> dict:
    """Request subscription deletion. Returns HITL_REQUIRED (I-27)."""
    agent = _get_agent()
    sub = agent.subscription_manager.get(subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found")
    return {
        "status": "HITL_REQUIRED",
        "subscription_id": subscription_id,
        "reason": "Subscription deletion requires Compliance Officer approval (I-27)",
    }


@router.post("/v1/webhooks/events", status_code=201)
async def publish_event(req: PublishEventRequest) -> dict:
    """Publish a webhook event. Creates delivery attempts for matching subscriptions.

    Returns event_id and delivery_attempt_count.
    Idempotent if idempotency_key is provided and event already published.
    """
    agent = _get_agent()
    try:
        return agent.publish_event(
            event_type_str=req.event_type,
            payload=req.payload,
            source_service=req.source_service,
            idempotency_key=req.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/webhooks/events/{event_id}")
async def get_event(event_id: str) -> dict:
    """Get event details and all delivery attempts."""
    agent = _get_agent()
    return agent.get_delivery_status(event_id=event_id)


@router.get("/v1/webhooks/events")
async def list_events(event_type: str = "", limit: int = 50) -> dict:
    """List published events, optionally filtered by event_type."""
    agent = _get_agent()
    return agent.list_events(event_type_str=event_type, limit=limit)


@router.get("/v1/webhooks/deliveries/{attempt_id}")
async def get_delivery_attempt(attempt_id: str) -> dict:
    """Get a specific delivery attempt by ID."""
    agent = _get_agent()
    delivery = agent.event_publisher.delivery_store.get(attempt_id)  # type: ignore[attr-defined]
    if delivery is None:
        raise HTTPException(status_code=404, detail=f"Delivery attempt {attempt_id} not found")
    return {
        "attempt_id": delivery.attempt_id,
        "event_id": delivery.event_id,
        "subscription_id": delivery.subscription_id,
        "status": delivery.status.value,
        "http_status": delivery.http_status,
        "attempt_number": delivery.attempt_number,
        "attempted_at": delivery.attempted_at.isoformat(),
    }


@router.post("/v1/webhooks/dlq/{attempt_id}/retry", status_code=201)
async def retry_dlq(attempt_id: str) -> dict:
    """Retry a dead-lettered delivery attempt.

    Old DLQ record preserved (append-only I-24). Returns new PENDING attempt.
    """
    agent = _get_agent()
    try:
        return agent.retry_dlq_item(attempt_id=attempt_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/webhooks/event-types")
async def list_event_types() -> dict:
    """List all supported webhook event types."""
    from services.webhook_orchestrator.models import EventType  # noqa: PLC0415

    return {"event_types": [et.value for et in EventType]}
