"""
tests/test_notification_hub/test_models.py
IL-NHB-01 | Phase 18 — models, enums, and in-memory store tests
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.notification_hub.models import (
    Channel,
    DeliveryRecord,
    DeliveryStatus,
    InMemoryChannelAdapter,
    InMemoryDeliveryStore,
    InMemoryPreferenceStore,
    InMemoryTemplateStore,
    Language,
    NotificationCategory,
    NotificationPreference,
    NotificationRequest,
    NotificationTemplate,
    Priority,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────

NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)


def _make_template() -> NotificationTemplate:
    return NotificationTemplate(
        id="tmpl-test",
        name="Test Template",
        category=NotificationCategory.PAYMENT,
        channel=Channel.EMAIL,
        language=Language.EN,
        subject="Hello {{ name }}",
        body="Body text",
        version="v1",
    )


def _make_preference(opt_in: bool = True) -> NotificationPreference:
    return NotificationPreference(
        entity_id="entity-001",
        channel=Channel.EMAIL,
        category=NotificationCategory.PAYMENT,
        opt_in=opt_in,
        updated_at=NOW,
    )


def _make_delivery_record(status: DeliveryStatus = DeliveryStatus.SENT) -> DeliveryRecord:
    return DeliveryRecord(
        id="rec-001",
        request_id="req-001",
        entity_id="entity-001",
        channel=Channel.EMAIL,
        status=status,
        attempted_at=NOW,
        delivered_at=NOW if status == DeliveryStatus.SENT else None,
        failure_reason=None,
        retry_count=0,
        rendered_subject="Subject",
        rendered_body="Body",
    )


def _make_request() -> NotificationRequest:
    return NotificationRequest(
        id="req-001",
        entity_id="entity-001",
        category=NotificationCategory.PAYMENT,
        channel=Channel.EMAIL,
        template_id="tmpl-payment-confirmed",
        context={"name": "Alice", "amount": "100"},
        priority=Priority.NORMAL,
        created_at=NOW,
        actor="system",
    )


# ─── NotificationTemplate tests ──────────────────────────────────────────────


def test_template_creation() -> None:
    t = _make_template()
    assert t.id == "tmpl-test"
    assert t.category == NotificationCategory.PAYMENT


def test_template_is_frozen() -> None:
    t = _make_template()
    with pytest.raises(AttributeError):
        t.id = "new-id"  # type: ignore[misc]


# ─── NotificationPreference tests ────────────────────────────────────────────


def test_preference_opt_in_true() -> None:
    p = _make_preference(opt_in=True)
    assert p.opt_in is True


def test_preference_opt_in_false() -> None:
    p = _make_preference(opt_in=False)
    assert p.opt_in is False


# ─── DeliveryRecord tests ─────────────────────────────────────────────────────


def test_delivery_record_defaults() -> None:
    r = _make_delivery_record()
    assert r.retry_count == 0
    assert r.status == DeliveryStatus.SENT


# ─── NotificationRequest tests ────────────────────────────────────────────────


def test_notification_request_context_dict() -> None:
    req = _make_request()
    assert isinstance(req.context, dict)
    assert req.context["name"] == "Alice"


# ─── InMemoryTemplateStore tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_template_store_seeded_with_3() -> None:
    store = InMemoryTemplateStore()
    templates = await store.list_templates()
    assert len(templates) == 3


@pytest.mark.asyncio
async def test_template_store_list_no_filter_returns_3() -> None:
    store = InMemoryTemplateStore()
    result = await store.list_templates()
    assert len(result) == 3


@pytest.mark.asyncio
async def test_template_store_filter_by_category_payment() -> None:
    store = InMemoryTemplateStore()
    result = await store.list_templates(category=NotificationCategory.PAYMENT)
    assert len(result) == 1
    assert result[0].id == "tmpl-payment-confirmed"


@pytest.mark.asyncio
async def test_template_store_filter_by_channel_email() -> None:
    store = InMemoryTemplateStore()
    result = await store.list_templates(channel=Channel.EMAIL)
    assert all(t.channel == Channel.EMAIL for t in result)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_template_store_get_existing() -> None:
    store = InMemoryTemplateStore()
    t = await store.get("tmpl-payment-confirmed")
    assert t is not None
    assert t.name == "Payment Confirmed"


@pytest.mark.asyncio
async def test_template_store_get_missing_returns_none() -> None:
    store = InMemoryTemplateStore()
    result = await store.get("non-existent")
    assert result is None


# ─── InMemoryPreferenceStore tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_preference_store_save_and_get() -> None:
    store = InMemoryPreferenceStore()
    pref = _make_preference()
    await store.save(pref)
    result = await store.get("entity-001", Channel.EMAIL, NotificationCategory.PAYMENT)
    assert result is not None
    assert result.opt_in is True


# ─── InMemoryDeliveryStore tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivery_store_save_get_list() -> None:
    store = InMemoryDeliveryStore()
    rec = _make_delivery_record()
    await store.save(rec)
    fetched = await store.get("rec-001")
    assert fetched is not None
    assert fetched.entity_id == "entity-001"
    listed = await store.list_by_entity("entity-001")
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_delivery_store_list_failed_only_failed() -> None:
    store = InMemoryDeliveryStore()
    ok_rec = _make_delivery_record(status=DeliveryStatus.SENT)
    failed_rec = DeliveryRecord(
        id="rec-002",
        request_id="req-002",
        entity_id="entity-001",
        channel=Channel.EMAIL,
        status=DeliveryStatus.FAILED,
        attempted_at=NOW,
        delivered_at=None,
        failure_reason="timeout",
        retry_count=1,
        rendered_subject=None,
        rendered_body="body",
    )
    await store.save(ok_rec)
    await store.save(failed_rec)
    failed = await store.list_failed()
    assert len(failed) == 1
    assert failed[0].id == "rec-002"


# ─── InMemoryChannelAdapter tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_channel_adapter_send_returns_true() -> None:
    adapter = InMemoryChannelAdapter(should_succeed=True)
    rec = _make_delivery_record()
    result = await adapter.send(rec)
    assert result is True


@pytest.mark.asyncio
async def test_channel_adapter_send_failure_returns_false() -> None:
    adapter = InMemoryChannelAdapter(should_succeed=False)
    rec = _make_delivery_record()
    result = await adapter.send(rec)
    assert result is False
