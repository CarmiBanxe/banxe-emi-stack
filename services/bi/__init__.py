"""
services/bi/__init__.py
BI Presentation Layer — Superset Dashboard Integration
GAP-043 L-bi | IL-CBS-GAP043-BI-2026-06-30

Apache Superset self-hosted analytics service.
Protocol DI: BIPort → InMemoryBIService (dev/test) → Real adapter (production)
"""

from __future__ import annotations

__all__ = ["BIPort", "InMemoryBIService"]
