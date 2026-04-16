"""
services/notification_hub/preference_manager.py
IL-NHB-01 | Phase 18

User notification preferences — opt-in/opt-out per channel per category.
GDPR-compliant: default opt-out for MARKETING, default opt-in for OPERATIONAL/SECURITY.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.notification_hub.models import (
    Channel,
    NotificationCategory,
    NotificationPreference,
    PreferenceStorePort,
)

# Default opt-in categories (apply when no stored preference exists)
_DEFAULT_OPT_IN = {NotificationCategory.SECURITY, NotificationCategory.OPERATIONAL}


class PreferenceManager:
    """Manages per-entity notification preferences with GDPR-compliant defaults."""

    def __init__(self, store: PreferenceStorePort) -> None:
        self._store = store

    async def is_opted_in(
        self,
        entity_id: str,
        channel: Channel,
        category: NotificationCategory,
    ) -> bool:
        """
        Return True if the entity is opted in for the given channel/category.

        Default behaviour (no stored preference):
          - SECURITY, OPERATIONAL → opt-in
          - All others → opt-out
        """
        pref = await self._store.get(entity_id, channel, category)
        if pref is not None:
            return pref.opt_in
        return category in _DEFAULT_OPT_IN

    async def set_preference(
        self,
        entity_id: str,
        channel: Channel,
        category: NotificationCategory,
        opt_in: bool,
    ) -> NotificationPreference:
        """Create or update a notification preference; persist and return it."""
        pref = NotificationPreference(
            entity_id=entity_id,
            channel=channel,
            category=category,
            opt_in=opt_in,
            updated_at=datetime.now(UTC),
        )
        await self._store.save(pref)
        return pref

    async def get_preferences(self, entity_id: str) -> list[NotificationPreference]:
        """Return all stored preferences for an entity."""
        return await self._store.list_by_entity(entity_id)

    async def opt_out_all(self, entity_id: str) -> int:
        """
        Opt-out the entity from all channel/category combinations.

        Returns:
            Number of preferences updated (= number of Channel × Category combinations).
        """
        count = 0
        for channel in Channel:
            for category in NotificationCategory:
                await self.set_preference(entity_id, channel, category, opt_in=False)
                count += 1
        return count
