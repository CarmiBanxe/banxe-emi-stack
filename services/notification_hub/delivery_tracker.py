"""
services/notification_hub/delivery_tracker.py
IL-NHB-01 | Phase 18

Delivery tracking with exponential backoff retry logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from services.notification_hub.models import (
    DeliveryRecord,
    DeliveryStorePort,
    NotificationRequest,
)


class DeliveryTracker:
    """
    Tracks delivery records and handles retry with exponential backoff.

    Set base_delay_secs=0 in tests to skip asyncio.sleep entirely.
    """

    def __init__(
        self,
        store: DeliveryStorePort,
        dispatcher: object,  # ChannelDispatcher — avoid circular import
        max_retries: int = 3,
        base_delay_secs: float = 0.0,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher
        self._max_retries = max_retries
        self._base_delay_secs = base_delay_secs

    async def track(self, record: DeliveryRecord) -> DeliveryRecord:
        """Persist the initial delivery record and return it."""
        await self._store.save(record)
        return record

    async def retry_failed(
        self,
        request: NotificationRequest,
        failed_record: DeliveryRecord,
        rendered_subject: str,
        rendered_body: str,
    ) -> DeliveryRecord:
        """
        Retry a failed delivery with exponential backoff.

        Returns the original failed_record unchanged if max_retries exceeded.
        """
        if failed_record.retry_count >= self._max_retries:
            return failed_record

        delay = self._base_delay_secs * (2**failed_record.retry_count)
        if delay > 0:
            await asyncio.sleep(min(delay, 30.0))

        new_record = await self._dispatcher.dispatch(  # type: ignore[union-attr]
            request, rendered_subject, rendered_body
        )
        # Carry forward the incremented retry count
        updated = replace(new_record, retry_count=failed_record.retry_count + 1)
        await self._store.save(updated)
        return updated

    async def get_status(self, record_id: str) -> DeliveryRecord | None:
        """Return a delivery record by ID, or None if not found."""
        return await self._store.get(record_id)

    async def list_failed(self) -> list[DeliveryRecord]:
        """Return all delivery records with FAILED status."""
        return await self._store.list_failed()

    async def get_entity_history(self, entity_id: str) -> list[DeliveryRecord]:
        """Return all delivery records for a given entity."""
        return await self._store.list_by_entity(entity_id)
