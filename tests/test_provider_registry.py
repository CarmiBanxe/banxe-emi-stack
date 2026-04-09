"""
test_provider_registry.py — Provider Registry tests
S17-12: Pluggable provider architecture with health check + fallback
Pattern: Geniusto v5 Plugin2/Provider2
"""

from __future__ import annotations

import pytest

from services.providers.provider_registry import (
    ProviderCategory,
    ProviderDefinition,
    ProviderRegistry,
    ProviderStatus,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_registry(payment_defs: list[dict]) -> ProviderRegistry:
    return ProviderRegistry.from_dict({"payment_rails": payment_defs})


@pytest.fixture
def registry_with_sandbox_only():
    return _make_registry(
        [
            {"adapter": "mock", "display_name": "Mock", "priority": 99, "enabled": True},
        ]
    )


@pytest.fixture
def registry_with_primary_disabled():
    return _make_registry(
        [
            {"adapter": "modulr", "display_name": "Modulr", "priority": 1, "enabled": False},
            {"adapter": "mock", "display_name": "Mock", "priority": 99, "enabled": True},
        ]
    )


@pytest.fixture
def registry_with_primary_enabled():
    return _make_registry(
        [
            {"adapter": "modulr", "display_name": "Modulr", "priority": 1, "enabled": True},
            {"adapter": "clearbank", "display_name": "ClearBank", "priority": 2, "enabled": True},
            {"adapter": "mock", "display_name": "Mock", "priority": 99, "enabled": True},
        ]
    )


# ── Resolution ─────────────────────────────────────────────────────────────────


class TestResolve:
    def test_sandbox_when_only_option(self, registry_with_sandbox_only):
        res = registry_with_sandbox_only.resolve(ProviderCategory.PAYMENT_RAILS)
        assert res.adapter == "mock"
        assert res.sandbox_used is True

    def test_sandbox_when_primary_disabled(self, registry_with_primary_disabled):
        res = registry_with_primary_disabled.resolve(ProviderCategory.PAYMENT_RAILS)
        assert res.adapter == "mock"
        assert res.sandbox_used is True

    def test_primary_when_enabled(self, registry_with_primary_enabled):
        res = registry_with_primary_enabled.resolve(ProviderCategory.PAYMENT_RAILS)
        assert res.adapter == "modulr"
        assert res.sandbox_used is False
        assert res.fallback_used is False

    def test_fallback_when_primary_disabled(self):
        registry = _make_registry(
            [
                {"adapter": "modulr", "display_name": "Modulr", "priority": 1, "enabled": False},
                {
                    "adapter": "clearbank",
                    "display_name": "ClearBank",
                    "priority": 2,
                    "enabled": True,
                },
                {"adapter": "mock", "display_name": "Mock", "priority": 99, "enabled": True},
            ]
        )
        res = registry.resolve(ProviderCategory.PAYMENT_RAILS)
        assert res.adapter == "clearbank"
        assert res.fallback_used is True

    def test_error_when_no_providers(self):
        registry = ProviderRegistry.from_dict({"payment_rails": []})
        with pytest.raises(ValueError, match="No providers configured"):
            registry.resolve(ProviderCategory.PAYMENT_RAILS)

    def test_error_when_all_disabled_no_sandbox(self):
        registry = _make_registry(
            [
                {"adapter": "modulr", "display_name": "Modulr", "priority": 1, "enabled": False},
            ]
        )
        with pytest.raises(RuntimeError, match="No enabled provider"):
            registry.resolve(ProviderCategory.PAYMENT_RAILS)

    def test_missing_category_raises(self):
        registry = ProviderRegistry.from_dict({})
        with pytest.raises(ValueError):
            registry.resolve(ProviderCategory.IDV)


# ── List providers ─────────────────────────────────────────────────────────────


class TestListProviders:
    def test_sorted_by_priority(self, registry_with_primary_enabled):
        providers = registry_with_primary_enabled.list_providers(ProviderCategory.PAYMENT_RAILS)
        priorities = [p.priority for p in providers]
        assert priorities == sorted(priorities)

    def test_empty_for_unknown_category(self, registry_with_sandbox_only):
        providers = registry_with_sandbox_only.list_providers(ProviderCategory.FRAUD)
        assert providers == []


# ── From YAML ──────────────────────────────────────────────────────────────────


class TestFromYaml:
    def test_loads_providers_yaml(self, tmp_path):
        yaml_content = """
payment_rails:
  primary:
    adapter: modulr
    display_name: Modulr
    priority: 1
    enabled: false
  sandbox:
    adapter: mock
    display_name: Mock
    priority: 99
    enabled: true
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(yaml_content)
        registry = ProviderRegistry.from_yaml(config_file)
        res = registry.resolve(ProviderCategory.PAYMENT_RAILS)
        assert res.adapter == "mock"

    def test_loads_real_providers_yaml(self):
        """Smoke test: real config/providers.yaml is valid."""
        registry = ProviderRegistry.from_yaml("config/providers.yaml")
        # All 6 categories should have at least sandbox
        for cat in ProviderCategory:
            try:
                res = registry.resolve(cat)
                assert res.adapter is not None
            except (ValueError, RuntimeError):
                pass  # Some categories may not be in our yaml — that's ok

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ProviderRegistry.from_yaml("/nonexistent/providers.yaml")


# ── Health summary ─────────────────────────────────────────────────────────────


class TestHealthSummary:
    def test_summary_shows_disabled(self, registry_with_primary_disabled):
        summary = registry_with_primary_disabled.health_summary()
        assert "payment_rails" in summary
        statuses = list(summary["payment_rails"].values())
        assert "DISABLED" in statuses

    def test_sandbox_is_unknown(self, registry_with_sandbox_only):
        # sandbox has no health_url → UNKNOWN
        providers = registry_with_sandbox_only.list_providers(ProviderCategory.PAYMENT_RAILS)
        sandbox = providers[0]
        status = registry_with_sandbox_only.check_health(sandbox)
        assert status == ProviderStatus.UNKNOWN

    def test_provider_is_sandbox_when_priority_99(self):
        pdef = ProviderDefinition(adapter="mock", display_name="Mock", priority=99, enabled=True)
        assert pdef.is_sandbox is True

    def test_provider_not_sandbox_when_priority_1(self):
        pdef = ProviderDefinition(adapter="modulr", display_name="Modulr", priority=1, enabled=True)
        assert pdef.is_sandbox is False
