"""
services/notification_hub/channel_dispatcher.py
IL-NHB-01 | Phase 18

Multi-channel notification dispatcher.
Delegates to channel adapters (SMTP, Twilio stub, FCM stub, Telegram, Webhook).
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.notification_hub.models import (
    Channel,
    ChannelAdapterPort,
    DeliveryRecord,
    DeliveryStatus,
    DeliveryStorePort,
    InMemoryChannelAdapter,
    NotificationRequest,
)


class ChannelDispatcher:
    """Dispatches notifications to channel-specific adapters and tracks records."""

    def __init__(
        self,
        adapters: dict[Channel, ChannelAdapterPort],
        delivery_store: DeliveryStorePort,
    ) -> None:
        self._adapters = adapters
        self._delivery_store = delivery_store

    async def dispatch(
        self,
        request: NotificationRequest,
        rendered_subject: str,
        rendered_body: str,
    ) -> DeliveryRecord:
        """
        Dispatch a notification via the appropriate channel adapter.

        Raises:
            ValueError: if no adapter is registered for the request's channel
        """
        if request.channel not in self._adapters:
            raise ValueError(f"No adapter registered for channel: {request.channel!r}")

        adapter = self._adapters[request.channel]
        now = datetime.now(UTC)

        pending_record = DeliveryRecord(
            id=str(uuid.uuid4()),
            request_id=request.id,
            entity_id=request.entity_id,
            channel=request.channel,
            status=DeliveryStatus.PENDING,
            attempted_at=now,
            delivered_at=None,
            failure_reason=None,
            retry_count=0,
            rendered_subject=rendered_subject,
            rendered_body=rendered_body,
        )

        success = await adapter.send(pending_record)

        if success:
            final_record = DeliveryRecord(
                id=pending_record.id,
                request_id=pending_record.request_id,
                entity_id=pending_record.entity_id,
                channel=pending_record.channel,
                status=DeliveryStatus.SENT,
                attempted_at=pending_record.attempted_at,
                delivered_at=datetime.now(UTC),
                failure_reason=None,
                retry_count=pending_record.retry_count,
                rendered_subject=pending_record.rendered_subject,
                rendered_body=pending_record.rendered_body,
            )
        else:
            final_record = DeliveryRecord(
                id=pending_record.id,
                request_id=pending_record.request_id,
                entity_id=pending_record.entity_id,
                channel=pending_record.channel,
                status=DeliveryStatus.FAILED,
                attempted_at=pending_record.attempted_at,
                delivered_at=None,
                failure_reason="Adapter returned failure",
                retry_count=pending_record.retry_count,
                rendered_subject=pending_record.rendered_subject,
                rendered_body=pending_record.rendered_body,
            )

        await self._delivery_store.save(final_record)
        return final_record

    async def get_delivery_status(self, record_id: str) -> DeliveryRecord | None:
        """Return a delivery record by ID, or None if not found."""
        return await self._delivery_store.get(record_id)

    @staticmethod
    def make_default_adapters(should_succeed: bool = True) -> dict[Channel, ChannelAdapterPort]:
        """Return a dict mapping all 5 channels to InMemoryChannelAdapter instances."""
        adapter = InMemoryChannelAdapter(should_succeed=should_succeed)
        return {
            Channel.EMAIL: adapter,
            Channel.SMS: adapter,
            Channel.PUSH: adapter,
            Channel.TELEGRAM: adapter,
            Channel.WEBHOOK: adapter,
        }
