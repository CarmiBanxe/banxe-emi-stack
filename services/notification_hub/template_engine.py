"""
services/notification_hub/template_engine.py
IL-NHB-01 | Phase 18

Jinja2-based notification template rendering with multi-language support (EN/FR/RU).
"""

from __future__ import annotations

from jinja2 import Environment, TemplateSyntaxError

from services.notification_hub.models import (
    Channel,
    NotificationCategory,
    NotificationTemplate,
    TemplateStorePort,
)

# Default (non-strict) environment — missing vars render as empty string
_ENV = Environment()  # nosec B701  # noqa: S701 — plain-text templates, not HTML


class TemplateEngine:
    """Renders Jinja2 notification templates with context variable substitution."""

    def __init__(self, store: TemplateStorePort) -> None:
        self._store = store

    async def render(self, template_id: str, context: dict) -> tuple[str, str]:  # type: ignore[type-arg]
        """
        Render a template by ID with the provided context.

        Returns:
            (rendered_subject, rendered_body) tuple

        Raises:
            ValueError: if template_id not found in store
        """
        template = await self._store.get(template_id)
        if template is None:
            raise ValueError(f"Template not found: {template_id!r}")

        rendered_subject = _ENV.from_string(template.subject).render(**context)
        rendered_body = _ENV.from_string(template.body).render(**context)
        return rendered_subject, rendered_body

    async def list_templates(
        self,
        category: NotificationCategory | None = None,
        channel: Channel | None = None,
    ) -> list[NotificationTemplate]:
        """Return templates optionally filtered by category and/or channel."""
        return await self._store.list_templates(category=category, channel=channel)

    async def validate_template(self, template: NotificationTemplate) -> list[str]:
        """
        Validate Jinja2 syntax in a template.

        Returns:
            Empty list if valid; list of error strings if syntax errors found.
            UndefinedError is NOT treated as an error — variables provided at send time.
        """
        errors: list[str] = []
        for source in (template.subject, template.body):
            try:
                _ENV.parse(source)
            except TemplateSyntaxError as exc:
                errors.append(str(exc))
        return errors
