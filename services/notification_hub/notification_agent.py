"""
services/notification_hub/notification_agent.py
IL-NHB-01 | Phase 18

Notification Agent — L2 orchestration (template → preference → dispatch → track).
No HITL gate needed: notifications are informational, not financial.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import uuid

from services.notification_hub.channel_dispatcher import ChannelDispatcher
from services.notification_hub.delivery_tracker import DeliveryTracker
from services.notification_hub.models import (
    Channel,
    NotificationCategory,
    NotificationRequest,
    Priority,
)
from services.notification_hub.preference_manager import PreferenceManager
from services.notification_hub.template_engine import TemplateEngine


def _record_to_dict(record: object) -> dict:  # type: ignore[type-arg]
    """Convert a frozen dataclass to a JSON-serialisable dict."""
    raw = asdict(record)  # type: ignore[arg-type]
    for key, val in raw.items():
        if hasattr(val, "value"):
            raw[key] = val.value
        elif isinstance(val, datetime):
            raw[key] = val.isoformat()
    return raw


def _pref_to_dict(pref: object) -> dict:  # type: ignore[type-arg]
    raw = asdict(pref)  # type: ignore[arg-type]
    for key, val in raw.items():
        if hasattr(val, "value"):
            raw[key] = val.value
        elif isinstance(val, datetime):
            raw[key] = val.isoformat()
    return raw


def _template_to_dict(tmpl: object) -> dict:  # type: ignore[type-arg]
    raw = asdict(tmpl)  # type: ignore[arg-type]
    for key, val in raw.items():
        if hasattr(val, "value"):
            raw[key] = val.value
    return raw


class NotificationAgent:
    """Orchestrates template rendering, preference checks, dispatch, and tracking."""

    def __init__(
        self,
        engine: TemplateEngine,
        dispatcher: ChannelDispatcher,
        preferences: PreferenceManager,
        tracker: DeliveryTracker,
    ) -> None:
        self._engine = engine
        self._dispatcher = dispatcher
        self._preferences = preferences
        self._tracker = tracker

    async def send(
        self,
        entity_id: str,
        category_str: str,
        channel_str: str,
        template_id: str,
        context: dict,  # type: ignore[type-arg]
        actor: str,
        priority_str: str = "NORMAL",
    ) -> dict:  # type: ignore[type-arg]
        """
        Send a notification to a single entity.

        Returns {"status": "OPT_OUT", "entity_id": entity_id} if entity opted out.
        """
        try:
            category = NotificationCategory(category_str.upper())
        except ValueError as exc:
            raise ValueError(f"Invalid category: {category_str!r}") from exc

        try:
            channel = Channel(channel_str.upper())
        except ValueError as exc:
            raise ValueError(f"Invalid channel: {channel_str!r}") from exc

        try:
            priority = Priority(priority_str.upper())
        except ValueError as exc:
            raise ValueError(f"Invalid priority: {priority_str!r}") from exc

        opted_in = await self._preferences.is_opted_in(entity_id, channel, category)
        if not opted_in:
            return {"status": "OPT_OUT", "entity_id": entity_id}

        request = NotificationRequest(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            category=category,
            channel=channel,
            template_id=template_id,
            context=context,
            priority=priority,
            created_at=datetime.now(UTC),
            actor=actor,
        )

        rendered_subject, rendered_body = await self._engine.render(template_id, context)
        record = await self._dispatcher.dispatch(request, rendered_subject, rendered_body)
        tracked = await self._tracker.track(record)
        return _record_to_dict(tracked)

    async def send_bulk(
        self,
        entity_ids: list[str],
        category_str: str,
        channel_str: str,
        template_id: str,
        context: dict,  # type: ignore[type-arg]
        actor: str,
    ) -> list[dict]:  # type: ignore[type-arg]
        """Send a notification to multiple entities; silently skip OPT_OUT entities."""
        results: list[dict] = []  # type: ignore[type-arg]
        for entity_id in entity_ids:
            result = await self.send(
                entity_id=entity_id,
                category_str=category_str,
                channel_str=channel_str,
                template_id=template_id,
                context=context,
                actor=actor,
            )
            if result.get("status") != "OPT_OUT":
                results.append(result)
        return results

    async def list_templates(
        self,
        category: str = "",
        channel: str = "",
    ) -> list[dict]:  # type: ignore[type-arg]
        """List templates, optionally filtered by category and/or channel."""
        cat = NotificationCategory(category.upper()) if category else None
        chan = Channel(channel.upper()) if channel else None
        templates = await self._engine.list_templates(category=cat, channel=chan)
        return [_template_to_dict(t) for t in templates]

    async def get_preferences(self, entity_id: str) -> list[dict]:  # type: ignore[type-arg]
        """Return all stored notification preferences for an entity."""
        prefs = await self._preferences.get_preferences(entity_id)
        return [_pref_to_dict(p) for p in prefs]

    async def set_preference(
        self,
        entity_id: str,
        channel_str: str,
        category_str: str,
        opt_in: bool,
    ) -> dict:  # type: ignore[type-arg]
        """Set a notification preference; return the preference as a dict."""
        channel = Channel(channel_str.upper())
        category = NotificationCategory(category_str.upper())
        pref = await self._preferences.set_preference(entity_id, channel, category, opt_in)
        return _pref_to_dict(pref)

    async def get_delivery_status(self, record_id: str) -> dict | None:  # type: ignore[type-arg]
        """Return a delivery record dict by ID, or None if not found."""
        record = await self._tracker.get_status(record_id)
        if record is None:
            return None
        return _record_to_dict(record)

    async def get_entity_history(self, entity_id: str) -> list[dict]:  # type: ignore[type-arg]
        """Return all delivery records for an entity as a list of dicts."""
        records = await self._tracker.get_entity_history(entity_id)
        return [_record_to_dict(r) for r in records]
