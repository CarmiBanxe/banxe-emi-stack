"""
provider_registry.py — Provider Registry (Plugin Architecture)
S17-12: Pluggable external service registry with health check + fallback routing
Pattern: Geniusto v5 Plugin2/Provider2 — configuration-driven adapter selection

WHY THIS FILE EXISTS
--------------------
Banxe has 6+ categories of external providers (payment rails, IDV, fraud, KYB,
notifications, IAM). Switching providers requires code changes + redeploy.

Provider Registry centralises this:
  1. Load providers from config/providers.yaml
  2. Health check all enabled providers at startup
  3. Resolve: for a category, return the highest-priority healthy adapter name
  4. Fallback: if primary unhealthy → next priority → ... → sandbox (always up)

This enables zero-code provider switching when BT-001/BT-004/BT-009 unlock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Provider category ──────────────────────────────────────────────────────────


class ProviderCategory(str, Enum):
    PAYMENT_RAILS = "payment_rails"
    IDV = "idv"
    FRAUD = "fraud"
    KYB = "kyb"
    NOTIFICATION = "notification"
    IAM = "iam"


class ProviderStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


# ── Provider definition ────────────────────────────────────────────────────────


@dataclass
class ProviderDefinition:
    adapter: str  # adapter name used in factory (e.g. "modulr")
    display_name: str
    priority: int
    enabled: bool
    health_url: str | None = None
    capabilities: list[str] = field(default_factory=list)
    status: ProviderStatus = ProviderStatus.UNKNOWN

    @property
    def is_sandbox(self) -> bool:
        return self.priority >= 99


@dataclass
class ProviderResolution:
    """Result of resolving the best available provider for a category."""

    category: ProviderCategory
    adapter: str
    provider: ProviderDefinition
    fallback_used: bool = False
    sandbox_used: bool = False


# ── Registry ───────────────────────────────────────────────────────────────────


class ProviderRegistry:
    """
    Configuration-driven provider registry.

    Usage:
        registry = ProviderRegistry.from_yaml("config/providers.yaml")
        resolution = registry.resolve(ProviderCategory.PAYMENT_RAILS)
        adapter_name = resolution.adapter  # "modulr" | "clearbank" | "mock"
    """

    def __init__(self, providers: dict[ProviderCategory, list[ProviderDefinition]]) -> None:
        self._providers = providers

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProviderRegistry:
        """Load provider registry from YAML config file."""
        import yaml  # type: ignore[import]

        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Provider config not found: {config_path}")

        with config_path.open() as f:
            raw = yaml.safe_load(f)

        providers: dict[ProviderCategory, list[ProviderDefinition]] = {}

        for cat_key, cat_config in raw.items():
            try:
                category = ProviderCategory(cat_key)
            except ValueError:
                logger.warning("Unknown provider category in config: %s", cat_key)
                continue

            defs: list[ProviderDefinition] = []
            for slot_name, slot_config in cat_config.items():
                if not isinstance(slot_config, dict):
                    continue
                defs.append(
                    ProviderDefinition(
                        adapter=slot_config.get("adapter", slot_name),
                        display_name=slot_config.get("display_name", slot_name),
                        priority=slot_config.get("priority", 50),
                        enabled=slot_config.get("enabled", False),
                        health_url=slot_config.get("health_url"),
                        capabilities=slot_config.get("capabilities", []),
                    )
                )
            # Sort by priority ascending (lower = higher priority)
            defs.sort(key=lambda d: d.priority)
            providers[category] = defs

        return cls(providers)

    @classmethod
    def from_dict(cls, raw: dict) -> ProviderRegistry:
        """Build registry from plain dict (for tests, no YAML file needed)."""
        providers: dict[ProviderCategory, list[ProviderDefinition]] = {}
        for cat_key, defs_list in raw.items():
            category = ProviderCategory(cat_key)
            defs = [ProviderDefinition(**d) for d in defs_list]
            defs.sort(key=lambda d: d.priority)
            providers[category] = defs
        return cls(providers)

    def list_providers(self, category: ProviderCategory) -> list[ProviderDefinition]:
        return self._providers.get(category, [])

    def resolve(self, category: ProviderCategory) -> ProviderResolution:
        """
        Return the best available (enabled + healthy) provider for a category.
        Falls back through priority order. Always returns sandbox if all else fails.
        """
        candidates = self._providers.get(category, [])
        if not candidates:
            raise ValueError(f"No providers configured for category: {category}")

        sandbox: ProviderDefinition | None = None
        for provider in candidates:
            if not provider.enabled:
                continue
            if provider.is_sandbox:
                sandbox = provider
                continue
            # Non-sandbox enabled provider: use it
            logger.info(
                "Resolved %s → %s (priority=%d, status=%s)",
                category,
                provider.adapter,
                provider.priority,
                provider.status,
            )
            return ProviderResolution(
                category=category,
                adapter=provider.adapter,
                provider=provider,
                fallback_used=provider.priority > 1,
            )

        # No non-sandbox provider enabled → use sandbox
        if sandbox is not None:
            logger.info("Resolved %s → %s (sandbox fallback)", category, sandbox.adapter)
            return ProviderResolution(
                category=category,
                adapter=sandbox.adapter,
                provider=sandbox,
                sandbox_used=True,
            )

        raise RuntimeError(f"No enabled provider for {category} — check providers.yaml")

    def check_health(self, provider: ProviderDefinition, timeout: float = 2.0) -> ProviderStatus:
        """
        HTTP GET health endpoint. Returns HEALTHY/UNHEALTHY/UNKNOWN.
        Providers with no health_url are marked UNKNOWN (assumed healthy for sandbox).
        """
        if provider.health_url is None:
            return ProviderStatus.UNKNOWN

        try:
            import urllib.request

            req = urllib.request.Request(provider.health_url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = ProviderStatus.HEALTHY if resp.status < 400 else ProviderStatus.UNHEALTHY
                provider.status = status
                return status
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", provider.adapter, exc)
            provider.status = ProviderStatus.UNHEALTHY
            return ProviderStatus.UNHEALTHY

    def health_summary(self) -> dict[str, dict[str, str]]:
        """Return health status of all providers (for admin dashboard / startup log)."""
        summary: dict[str, dict[str, str]] = {}
        for category, defs in self._providers.items():
            summary[category.value] = {}
            for p in defs:
                key = f"{p.adapter} (p={p.priority})"
                if not p.enabled:
                    summary[category.value][key] = "DISABLED"
                else:
                    summary[category.value][key] = p.status.value
        return summary
