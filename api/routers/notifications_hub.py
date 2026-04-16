"""
api/routers/notifications_hub.py
IL-NHB-01 | Phase 18

Notification Hub REST API — multi-channel notification management.

POST /v1/notifications-hub/send               — send notification
POST /v1/notifications-hub/send-bulk          — send to multiple entities
GET  /v1/notifications-hub/templates          — list templates (query: category, channel)
GET  /v1/notifications-hub/preferences/{id}   — get entity preferences
POST /v1/notifications-hub/preferences/{id}   — set preference
GET  /v1/notifications-hub/delivery/{id}      — get delivery status
GET  /v1/notifications-hub/history/{id}       — entity notification history
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.notification_hub.channel_dispatcher import ChannelDispatcher
from services.notification_hub.delivery_tracker import DeliveryTracker
from services.notification_hub.models import (
    InMemoryDeliveryStore,
    InMemoryPreferenceStore,
    InMemoryTemplateStore,
)
from services.notification_hub.notification_agent import NotificationAgent
from services.notification_hub.preference_manager import PreferenceManager
from services.notification_hub.template_engine import TemplateEngine

router = APIRouter(prefix="/notifications-hub", tags=["notifications-hub"])


# ─── Dependency injection ─────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> NotificationAgent:
    template_store = InMemoryTemplateStore()
    preference_store = InMemoryPreferenceStore()
    delivery_store = InMemoryDeliveryStore()

    engine = TemplateEngine(store=template_store)
    adapters = ChannelDispatcher.make_default_adapters(should_succeed=True)
    dispatcher = ChannelDispatcher(adapters=adapters, delivery_store=delivery_store)
    preferences = PreferenceManager(store=preference_store)
    tracker = DeliveryTracker(store=delivery_store, dispatcher=dispatcher, base_delay_secs=0.0)

    return NotificationAgent(
        engine=engine,
        dispatcher=dispatcher,
        preferences=preferences,
        tracker=tracker,
    )


# ─── Request models ───────────────────────────────────────────────────────────


class SendNotificationRequest(BaseModel):
    entity_id: str = Field(..., description="Customer or firm ID")
    category: str = Field(..., description="Notification category (e.g. PAYMENT, KYC)")
    channel: str = Field(..., description="Delivery channel (e.g. EMAIL, SMS)")
    template_id: str = Field(..., description="Template ID to render")
    context: dict = Field(default_factory=dict, description="Template variables")  # type: ignore[type-arg]
    actor: str = Field(..., description="System or user initiating the notification")
    priority: str = Field(default="NORMAL", description="Priority: LOW/NORMAL/HIGH/CRITICAL")


class SendBulkRequest(BaseModel):
    entity_ids: list[str] = Field(..., description="List of entity IDs to notify")
    category: str = Field(..., description="Notification category")
    channel: str = Field(..., description="Delivery channel")
    template_id: str = Field(..., description="Template ID to render")
    context: dict = Field(default_factory=dict, description="Template variables")  # type: ignore[type-arg]
    actor: str = Field(..., description="System or user initiating the notification")


class SetPreferenceRequest(BaseModel):
    channel: str = Field(..., description="Delivery channel")
    category: str = Field(..., description="Notification category")
    opt_in: bool = Field(..., description="True to opt in, False to opt out")


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/send", summary="Send a notification to a single entity")
async def send_notification(body: SendNotificationRequest) -> dict:  # type: ignore[type-arg]
    """
    Dispatch a notification to the specified entity via template rendering.
    Returns OPT_OUT status if the entity has opted out for the given channel/category.
    """
    agent = _get_agent()
    try:
        result = await agent.send(
            entity_id=body.entity_id,
            category_str=body.category,
            channel_str=body.channel,
            template_id=body.template_id,
            context=body.context,
            actor=body.actor,
            priority_str=body.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.post("/send-bulk", summary="Send a notification to multiple entities")
async def send_bulk(body: SendBulkRequest) -> list[dict]:  # type: ignore[type-arg]
    """
    Dispatch the same notification to multiple entities.
    Entities that are opted out are silently skipped.
    """
    agent = _get_agent()
    try:
        results = await agent.send_bulk(
            entity_ids=body.entity_ids,
            category_str=body.category,
            channel_str=body.channel,
            template_id=body.template_id,
            context=body.context,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return results


@router.get("/templates", summary="List notification templates")
async def list_templates(
    category: Annotated[str, Query(description="Filter by category")] = "",
    channel: Annotated[str, Query(description="Filter by channel")] = "",
) -> list[dict]:  # type: ignore[type-arg]
    """Return all available notification templates, optionally filtered."""
    agent = _get_agent()
    try:
        return await agent.list_templates(category=category, channel=channel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/preferences/{entity_id}",
    summary="Get notification preferences for an entity",
)
async def get_preferences(entity_id: str) -> list[dict]:  # type: ignore[type-arg]
    """Return all stored notification preferences for the given entity."""
    agent = _get_agent()
    return await agent.get_preferences(entity_id)


@router.post(
    "/preferences/{entity_id}",
    summary="Set a notification preference for an entity",
)
async def set_preference(entity_id: str, body: SetPreferenceRequest) -> dict:  # type: ignore[type-arg]
    """Create or update a notification preference (opt-in or opt-out)."""
    agent = _get_agent()
    try:
        return await agent.set_preference(
            entity_id=entity_id,
            channel_str=body.channel,
            category_str=body.category,
            opt_in=body.opt_in,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/delivery/{record_id}",
    summary="Get delivery status for a notification record",
)
async def get_delivery_status(record_id: str) -> dict:  # type: ignore[type-arg]
    """Return the delivery record for the given ID, or 404 if not found."""
    agent = _get_agent()
    result = await agent.get_delivery_status(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Delivery record not found: {record_id!r}")
    return result


@router.get(
    "/history/{entity_id}",
    summary="Get notification history for an entity",
)
async def get_entity_history(entity_id: str) -> list[dict]:  # type: ignore[type-arg]
    """Return all delivery records for the given entity."""
    agent = _get_agent()
    return await agent.get_entity_history(entity_id)
