"""
tests/test_notification_hub/test_channel_dispatcher.py
IL-NHB-01 | Phase 18 — ChannelDispatcher tests
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.notification_hub.channel_dispatcher import ChannelDispatcher
from services.notification_hub.models import (
    Channel,
    DeliveryStatus,
    InMemoryDeliveryStore,
    NotificationCategory,
    NotificationRequest,
    Priority,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)


def _make_request(channel: Channel = Channel.EMAIL) -> NotificationRequest:
    return NotificationRequest(
        id="req-001",
        entity_id="entity-001",
        category=NotificationCategory.PAYMENT,
        channel=channel,
        template_id="tmpl-payment-confirmed",
        context={"name": "Alice"},
        priority=Priority.NORMAL,
        created_at=NOW,
        actor="system",
    )


def _make_dispatcher(
    should_succeed: bool = True,
) -> tuple[ChannelDispatcher, InMemoryDeliveryStore]:
    store = InMemoryDeliveryStore()
    adapters = ChannelDispatcher.make_default_adapters(should_succeed=should_succeed)
    dispatcher = ChannelDispatcher(adapters=adapters, delivery_store=store)
    return dispatcher, store


# ─── dispatch() tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_returns_delivery_record() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request()
    record = await dispatcher.dispatch(req, "Subject", "Body text")
    assert record is not None
    assert record.id is not None


@pytest.mark.asyncio
async def test_dispatch_status_sent_on_success() -> None:
    dispatcher, _ = _make_dispatcher(should_succeed=True)
    record = await dispatcher.dispatch(_make_request(), "Subject", "Body")
    assert record.status == DeliveryStatus.SENT


@pytest.mark.asyncio
async def test_dispatch_status_failed_when_adapter_fails() -> None:
    dispatcher, _ = _make_dispatcher(should_succeed=False)
    record = await dispatcher.dispatch(_make_request(), "Subject", "Body")
    assert record.status == DeliveryStatus.FAILED


@pytest.mark.asyncio
async def test_dispatch_record_saved_to_store() -> None:
    dispatcher, store = _make_dispatcher()
    req = _make_request()
    record = await dispatcher.dispatch(req, "Subject", "Body")
    fetched = await store.get(record.id)
    assert fetched is not None
    assert fetched.id == record.id


@pytest.mark.asyncio
async def test_dispatch_no_adapter_raises_value_error() -> None:
    store = InMemoryDeliveryStore()
    dispatcher = ChannelDispatcher(adapters={}, delivery_store=store)
    req = _make_request(channel=Channel.EMAIL)
    with pytest.raises(ValueError, match="No adapter registered"):
        await dispatcher.dispatch(req, "Subject", "Body")


@pytest.mark.asyncio
async def test_dispatch_rendered_body_stored_in_record() -> None:
    dispatcher, _ = _make_dispatcher()
    record = await dispatcher.dispatch(_make_request(), "Subj", "My rendered body content")
    assert record.rendered_body == "My rendered body content"


@pytest.mark.asyncio
async def test_dispatch_rendered_subject_stored_in_record() -> None:
    dispatcher, _ = _make_dispatcher()
    record = await dispatcher.dispatch(_make_request(), "My rendered subject", "Body")
    assert record.rendered_subject == "My rendered subject"


# ─── get_delivery_status() tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_delivery_status_existing_record() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request()
    record = await dispatcher.dispatch(req, "S", "B")
    fetched = await dispatcher.get_delivery_status(record.id)
    assert fetched is not None
    assert fetched.id == record.id


@pytest.mark.asyncio
async def test_get_delivery_status_none_for_missing() -> None:
    dispatcher, _ = _make_dispatcher()
    result = await dispatcher.get_delivery_status("non-existent-id")
    assert result is None


# ─── make_default_adapters() tests ────────────────────────────────────────────


def test_make_default_adapters_returns_5_channels() -> None:
    adapters = ChannelDispatcher.make_default_adapters()
    assert len(adapters) == 5
    assert Channel.EMAIL in adapters
    assert Channel.SMS in adapters
    assert Channel.PUSH in adapters
    assert Channel.TELEGRAM in adapters
    assert Channel.WEBHOOK in adapters


# ─── Per-channel dispatch tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_via_email_channel() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request(channel=Channel.EMAIL)
    record = await dispatcher.dispatch(req, "Subject", "Body")
    assert record.channel == Channel.EMAIL
    assert record.status == DeliveryStatus.SENT


@pytest.mark.asyncio
async def test_dispatch_via_sms_channel() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request(channel=Channel.SMS)
    record = await dispatcher.dispatch(req, "", "SMS text")
    assert record.channel == Channel.SMS
    assert record.status == DeliveryStatus.SENT


@pytest.mark.asyncio
async def test_dispatch_via_telegram_channel() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request(channel=Channel.TELEGRAM)
    record = await dispatcher.dispatch(req, "", "Telegram message")
    assert record.channel == Channel.TELEGRAM
    assert record.status == DeliveryStatus.SENT


@pytest.mark.asyncio
async def test_dispatch_entity_id_preserved() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request()
    record = await dispatcher.dispatch(req, "S", "B")
    assert record.entity_id == "entity-001"


@pytest.mark.asyncio
async def test_dispatch_request_id_matches_request() -> None:
    dispatcher, _ = _make_dispatcher()
    req = _make_request()
    record = await dispatcher.dispatch(req, "S", "B")
    assert record.request_id == req.id
