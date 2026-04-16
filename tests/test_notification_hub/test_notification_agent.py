"""
tests/test_notification_hub/test_notification_agent.py
IL-NHB-01 | Phase 18 — NotificationAgent tests
"""

from __future__ import annotations

import pytest

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

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_agent(should_succeed: bool = True) -> NotificationAgent:
    template_store = InMemoryTemplateStore()
    preference_store = InMemoryPreferenceStore()
    delivery_store = InMemoryDeliveryStore()

    engine = TemplateEngine(store=template_store)
    adapters = ChannelDispatcher.make_default_adapters(should_succeed=should_succeed)
    dispatcher = ChannelDispatcher(adapters=adapters, delivery_store=delivery_store)
    preferences = PreferenceManager(store=preference_store)
    tracker = DeliveryTracker(store=delivery_store, dispatcher=dispatcher, base_delay_secs=0.0)

    return NotificationAgent(
        engine=engine,
        dispatcher=dispatcher,
        preferences=preferences,
        tracker=tracker,
    )


_PAYMENT_CTX = {
    "name": "Alice",
    "amount": "100.00",
    "currency": "EUR",
    "beneficiary": "Bob",
    "reference": "PAY-001",
}


# ─── send() tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_success_returns_dict_with_status() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "Alice"},
        actor="system",
    )
    assert isinstance(result, dict)
    assert "status" in result


@pytest.mark.asyncio
async def test_send_delivery_record_status_sent() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "Alice"},
        actor="system",
    )
    assert result["status"] == "SENT"


@pytest.mark.asyncio
async def test_send_opted_out_category_returns_opt_out() -> None:
    agent = _make_agent()
    # PAYMENT is opt-out by default
    result = await agent.send(
        entity_id="entity-opt-out",
        category_str="PAYMENT",
        channel_str="EMAIL",
        template_id="tmpl-payment-confirmed",
        context=_PAYMENT_CTX,
        actor="system",
    )
    assert result["status"] == "OPT_OUT"
    assert result["entity_id"] == "entity-opt-out"


@pytest.mark.asyncio
async def test_send_security_default_opt_in_delivers() -> None:
    agent = _make_agent()
    # SECURITY is default opt-in
    result = await agent.send(
        entity_id="entity-002",
        category_str="SECURITY",
        channel_str="SMS",
        template_id="tmpl-security-alert",
        context={"message": "Suspicious login"},
        actor="system",
    )
    assert result["status"] == "SENT"


@pytest.mark.asyncio
async def test_send_unknown_template_raises_value_error() -> None:
    agent = _make_agent()
    with pytest.raises(ValueError, match="Template not found"):
        await agent.send(
            entity_id="entity-001",
            category_str="OPERATIONAL",
            channel_str="EMAIL",
            template_id="non-existent",
            context={},
            actor="system",
        )


@pytest.mark.asyncio
async def test_send_invalid_category_raises_value_error() -> None:
    agent = _make_agent()
    with pytest.raises(ValueError, match="Invalid category"):
        await agent.send(
            entity_id="entity-001",
            category_str="INVALID_CATEGORY",
            channel_str="EMAIL",
            template_id="tmpl-kyc-approved",
            context={},
            actor="system",
        )


# ─── send_bulk() tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_bulk_two_entities_returns_two_results() -> None:
    agent = _make_agent()
    results = await agent.send_bulk(
        entity_ids=["e-001", "e-002"],
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "User"},
        actor="system",
    )
    assert len(results) == 2


@pytest.mark.asyncio
async def test_send_bulk_empty_entity_ids_returns_empty_list() -> None:
    agent = _make_agent()
    results = await agent.send_bulk(
        entity_ids=[],
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={},
        actor="system",
    )
    assert results == []


# ─── list_templates() tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_templates_returns_at_least_3() -> None:
    agent = _make_agent()
    result = await agent.list_templates()
    assert len(result) >= 3


@pytest.mark.asyncio
async def test_list_templates_filter_by_payment_category() -> None:
    agent = _make_agent()
    result = await agent.list_templates(category="PAYMENT")
    assert len(result) == 1
    assert result[0]["id"] == "tmpl-payment-confirmed"


# ─── get_preferences() tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_preferences_returns_list() -> None:
    agent = _make_agent()
    result = await agent.get_preferences("entity-001")
    assert isinstance(result, list)


# ─── set_preference() tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_preference_opt_in_returns_pref_dict() -> None:
    agent = _make_agent()
    result = await agent.set_preference(
        entity_id="entity-001",
        channel_str="EMAIL",
        category_str="PAYMENT",
        opt_in=True,
    )
    assert isinstance(result, dict)
    assert result["opt_in"] is True


# ─── get_delivery_status() tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_delivery_status_returns_record_after_send() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "Alice"},
        actor="system",
    )
    record_id = result["id"]
    status = await agent.get_delivery_status(record_id)
    assert status is not None
    assert status["id"] == record_id


# ─── get_entity_history() tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entity_history_returns_list() -> None:
    agent = _make_agent()
    await agent.send(
        entity_id="entity-history-001",
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "Alice"},
        actor="system",
    )
    history = await agent.get_entity_history("entity-history-001")
    assert len(history) >= 1


# ─── Priority test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_with_high_priority() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "Alice"},
        actor="system",
        priority_str="HIGH",
    )
    assert result["status"] == "SENT"


# ─── Context rendering test ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_context_variables_rendered_in_body() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="SECURITY",
        channel_str="SMS",
        template_id="tmpl-security-alert",
        context={"message": "Account locked by admin"},
        actor="system",
    )
    assert result["status"] == "SENT"
    assert "Account locked by admin" in result["rendered_body"]


# ─── Bulk mixed opt-in/opt-out test ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_bulk_mixed_opted_entities() -> None:
    agent = _make_agent()
    # OPERATIONAL: e-opt-001 default opt-in, e-opt-002 manually opted out
    await agent.set_preference("e-opt-002", "EMAIL", "OPERATIONAL", False)
    results = await agent.send_bulk(
        entity_ids=["e-opt-001", "e-opt-002", "e-opt-003"],
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "User"},
        actor="system",
    )
    # e-opt-001 and e-opt-003 are default opt-in, e-opt-002 is opted out (silently skipped)
    assert len(results) == 2


# ─── Channel-specific tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_email_uses_email_adapter() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="OPERATIONAL",
        channel_str="EMAIL",
        template_id="tmpl-kyc-approved",
        context={"name": "Alice"},
        actor="system",
    )
    assert result["channel"] == "EMAIL"


@pytest.mark.asyncio
async def test_send_sms_uses_sms_adapter() -> None:
    agent = _make_agent()
    result = await agent.send(
        entity_id="entity-001",
        category_str="SECURITY",
        channel_str="SMS",
        template_id="tmpl-security-alert",
        context={"message": "Test"},
        actor="system",
    )
    assert result["channel"] == "SMS"


# ─── Two sends → history has 2 records ───────────────────────────────────────


@pytest.mark.asyncio
async def test_two_sends_same_entity_history_has_two_records() -> None:
    agent = _make_agent()
    entity_id = "entity-two-sends"
    for _ in range(2):
        await agent.send(
            entity_id=entity_id,
            category_str="SECURITY",
            channel_str="SMS",
            template_id="tmpl-security-alert",
            context={"message": "Alert"},
            actor="system",
        )
    history = await agent.get_entity_history(entity_id)
    assert len(history) == 2
