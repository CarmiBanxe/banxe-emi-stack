"""
tests/test_notification_hub/test_template_engine.py
IL-NHB-01 | Phase 18 — TemplateEngine tests
"""

from __future__ import annotations

import pytest

from services.notification_hub.models import (
    Channel,
    InMemoryTemplateStore,
    Language,
    NotificationCategory,
    NotificationTemplate,
)
from services.notification_hub.template_engine import TemplateEngine

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_engine() -> TemplateEngine:
    return TemplateEngine(store=InMemoryTemplateStore())


# ─── render() tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_render_returns_tuple() -> None:
    engine = _make_engine()
    result = await engine.render(
        "tmpl-payment-confirmed",
        {
            "amount": "100",
            "currency": "EUR",
            "name": "Bob",
            "beneficiary": "Alice",
            "reference": "REF001",
        },
    )
    assert isinstance(result, tuple)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_render_subject_variables_substituted() -> None:
    engine = _make_engine()
    subject, _ = await engine.render(
        "tmpl-payment-confirmed",
        {
            "amount": "250.00",
            "currency": "GBP",
            "name": "Carol",
            "beneficiary": "Dave",
            "reference": "R999",
        },
    )
    assert "250.00" in subject
    assert "GBP" in subject


@pytest.mark.asyncio
async def test_render_body_variables_substituted() -> None:
    engine = _make_engine()
    _, body = await engine.render(
        "tmpl-payment-confirmed",
        {
            "amount": "50",
            "currency": "USD",
            "name": "Eve",
            "beneficiary": "Frank",
            "reference": "R123",
        },
    )
    assert "Eve" in body
    assert "Frank" in body


@pytest.mark.asyncio
async def test_render_missing_template_raises_value_error() -> None:
    engine = _make_engine()
    with pytest.raises(ValueError, match="Template not found"):
        await engine.render("non-existent-template", {})


@pytest.mark.asyncio
async def test_render_partial_context_missing_vars_empty_string() -> None:
    engine = _make_engine()
    # tmpl-kyc-approved uses {{ name }} — missing var renders as empty string
    _, body = await engine.render("tmpl-kyc-approved", {})
    assert "Dear" in body
    # name is missing → rendered as empty string (default jinja2 behavior)


@pytest.mark.asyncio
async def test_render_multi_variable_context() -> None:
    store = InMemoryTemplateStore()
    store._store["tmpl-multi"] = NotificationTemplate(
        id="tmpl-multi",
        name="Multi",
        category=NotificationCategory.OPERATIONAL,
        channel=Channel.EMAIL,
        language=Language.EN,
        subject="{{ name }} {{ amount }}",
        body="Hi {{ name }}, amount={{ amount }}",
        version="v1",
    )
    engine = TemplateEngine(store=store)
    subject, body = await engine.render("tmpl-multi", {"name": "Grace", "amount": "99"})
    assert subject == "Grace 99"
    assert "Grace" in body
    assert "99" in body


@pytest.mark.asyncio
async def test_list_templates_returns_3() -> None:
    engine = _make_engine()
    templates = await engine.list_templates()
    assert len(templates) == 3


@pytest.mark.asyncio
async def test_list_templates_filter_category_payment() -> None:
    engine = _make_engine()
    result = await engine.list_templates(category=NotificationCategory.PAYMENT)
    assert len(result) == 1
    assert result[0].id == "tmpl-payment-confirmed"


@pytest.mark.asyncio
async def test_list_templates_filter_channel_email() -> None:
    engine = _make_engine()
    result = await engine.list_templates(channel=Channel.EMAIL)
    assert all(t.channel == Channel.EMAIL for t in result)


@pytest.mark.asyncio
async def test_validate_template_valid_returns_empty() -> None:
    engine = _make_engine()
    store = InMemoryTemplateStore()
    valid_tmpl = await store.get("tmpl-kyc-approved")
    assert valid_tmpl is not None
    errors = await engine.validate_template(valid_tmpl)
    assert errors == []


@pytest.mark.asyncio
async def test_validate_template_syntax_error_returns_list() -> None:
    engine = _make_engine()
    bad_tmpl = NotificationTemplate(
        id="tmpl-bad",
        name="Bad",
        category=NotificationCategory.OPERATIONAL,
        channel=Channel.EMAIL,
        language=Language.EN,
        subject="OK",
        body="{% if %}broken",
        version="v1",
    )
    errors = await engine.validate_template(bad_tmpl)
    assert len(errors) > 0
    assert isinstance(errors[0], str)


@pytest.mark.asyncio
async def test_render_payment_template_amount_substituted() -> None:
    engine = _make_engine()
    subject, body = await engine.render(
        "tmpl-payment-confirmed",
        {
            "amount": "999.99",
            "currency": "EUR",
            "name": "Henry",
            "beneficiary": "Irene",
            "reference": "PAY-777",
        },
    )
    assert "999.99" in subject
    assert "999.99" in body


@pytest.mark.asyncio
async def test_render_security_template() -> None:
    engine = _make_engine()
    _, body = await engine.render(
        "tmpl-security-alert",
        {"message": "Suspicious login detected"},
    )
    assert "Suspicious login detected" in body
    assert "BANXE ALERT" in body


@pytest.mark.asyncio
async def test_render_with_empty_context() -> None:
    engine = _make_engine()
    # Should not raise — missing vars render as empty
    subject, body = await engine.render("tmpl-kyc-approved", {})
    assert isinstance(subject, str)
    assert isinstance(body, str)


@pytest.mark.asyncio
async def test_render_template_with_special_characters() -> None:
    store = InMemoryTemplateStore()
    store._store["tmpl-special"] = NotificationTemplate(
        id="tmpl-special",
        name="Special",
        category=NotificationCategory.OPERATIONAL,
        channel=Channel.EMAIL,
        language=Language.EN,
        subject="Alert: {{ title }}",
        body="Body: <b>bold</b> & {{ detail }}",
        version="v1",
    )
    engine = TemplateEngine(store=store)
    _, body = await engine.render("tmpl-special", {"title": "Test", "detail": "info"})
    assert "<b>bold</b>" in body
    assert "info" in body
