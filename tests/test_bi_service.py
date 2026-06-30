"""
tests/test_bi_service.py
BI Service Unit Tests
GAP-043 L-bi | IL-CBS-GAP043-BI-2026-06-30

Test suite for InMemoryBIService and BIPort protocol compliance.
≥15 tests covering:
  - Status retrieval and structure
  - Datasource listing and manipulation
  - Protocol conformance (duck-typing)
  - Edge cases and error scenarios
I-01: All test amounts/scores use Decimal (not float)
"""

from __future__ import annotations

from services.bi.bi_port import BIPort
from services.bi.bi_service import InMemoryBIService


class TestInMemoryBIServiceStatus:
    """Test get_status() behavior."""

    def test_get_status_returns_dict(self) -> None:
        """get_status() returns a dict."""
        service = InMemoryBIService()
        status = service.get_status()
        assert isinstance(status, dict)

    def test_get_status_has_status_key(self) -> None:
        """get_status() dict includes 'status' key."""
        service = InMemoryBIService()
        status = service.get_status()
        assert "status" in status

    def test_get_status_default_is_ok(self) -> None:
        """get_status() returns 'ok' by default."""
        service = InMemoryBIService()
        status = service.get_status()
        assert status["status"] == "ok"

    def test_get_status_provider_is_superset(self) -> None:
        """get_status() provider is 'superset'."""
        service = InMemoryBIService()
        status = service.get_status()
        assert status["provider"] == "superset"

    def test_get_status_version_is_semver(self) -> None:
        """get_status() version is semantic versioning string."""
        service = InMemoryBIService()
        status = service.get_status()
        assert "version" in status
        assert status["version"] == "4.1.1"

    def test_get_status_all_values_are_strings(self) -> None:
        """get_status() all values are strings."""
        service = InMemoryBIService()
        status = service.get_status()
        for key, value in status.items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestInMemoryBIServiceDatasources:
    """Test datasource listing and management."""

    def test_list_datasources_returns_list(self) -> None:
        """list_datasources() returns a list."""
        service = InMemoryBIService()
        datasources = service.list_datasources()
        assert isinstance(datasources, list)

    def test_list_datasources_non_empty(self) -> None:
        """list_datasources() returns non-empty list by default."""
        service = InMemoryBIService()
        datasources = service.list_datasources()
        assert len(datasources) > 0

    def test_list_datasources_includes_reporting_analytics(self) -> None:
        """list_datasources() includes 'reporting_analytics'."""
        service = InMemoryBIService()
        datasources = service.list_datasources()
        assert "reporting_analytics" in datasources

    def test_list_datasources_includes_safeguarding(self) -> None:
        """list_datasources() includes 'safeguarding'."""
        service = InMemoryBIService()
        datasources = service.list_datasources()
        assert "safeguarding" in datasources

    def test_list_datasources_includes_clickhouse_audit(self) -> None:
        """list_datasources() includes 'clickhouse_audit'."""
        service = InMemoryBIService()
        datasources = service.list_datasources()
        assert "clickhouse_audit" in datasources

    def test_list_datasources_all_strings(self) -> None:
        """list_datasources() all entries are strings."""
        service = InMemoryBIService()
        datasources = service.list_datasources()
        for ds in datasources:
            assert isinstance(ds, str)

    def test_add_datasource_appends_new_source(self) -> None:
        """add_datasource() adds a new datasource."""
        service = InMemoryBIService()
        original_count = len(service.list_datasources())
        service.add_datasource("new_datasource")
        assert len(service.list_datasources()) == original_count + 1
        assert "new_datasource" in service.list_datasources()

    def test_add_datasource_no_duplicate(self) -> None:
        """add_datasource() does not duplicate existing datasource."""
        service = InMemoryBIService()
        original_count = len(service.list_datasources())
        service.add_datasource("reporting_analytics")
        # Count should not increase
        assert len(service.list_datasources()) == original_count
        # reporting_analytics still in list
        assert "reporting_analytics" in service.list_datasources()


class TestInMemoryBIServiceStateManagement:
    """Test state mutation and reset."""

    def test_set_status_changes_status(self) -> None:
        """set_status() updates the status."""
        service = InMemoryBIService()
        service.set_status("error")
        status = service.get_status()
        assert status["status"] == "error"

    def test_reset_restores_defaults(self) -> None:
        """reset() restores default state."""
        service = InMemoryBIService()
        service.set_status("error")
        service.add_datasource("custom_ds")
        service.reset()

        # Status restored to ok
        assert service.get_status()["status"] == "ok"

        # Datasources restored to defaults
        datasources = service.list_datasources()
        assert len(datasources) == 3
        assert "reporting_analytics" in datasources
        assert "custom_ds" not in datasources


class TestBIPortProtocolConformance:
    """Test that InMemoryBIService satisfies BIPort protocol."""

    def test_bi_port_protocol_methods_exist(self) -> None:
        """InMemoryBIService has all required BIPort methods."""
        service = InMemoryBIService()
        # Check that required methods are callable
        assert callable(service.get_status)
        assert callable(service.list_datasources)

    def test_protocol_structural_typing(self) -> None:
        """InMemoryBIService satisfies BIPort contract (duck-typing)."""
        service: BIPort = InMemoryBIService()  # type: ignore

        # BIPort contract: get_status() returns dict[str, str]
        status = service.get_status()
        assert isinstance(status, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in status.items())

        # BIPort contract: list_datasources() returns list[str]
        datasources = service.list_datasources()
        assert isinstance(datasources, list)
        assert all(isinstance(ds, str) for ds in datasources)

    def test_initialization_idempotent(self) -> None:
        """Multiple instances start in same state."""
        service1 = InMemoryBIService()
        service2 = InMemoryBIService()

        assert service1.get_status() == service2.get_status()
        assert service1.list_datasources() == service2.list_datasources()

    def test_service_instances_are_isolated(self) -> None:
        """Service instances don't share state."""
        service1 = InMemoryBIService()
        service2 = InMemoryBIService()

        service1.add_datasource("instance1_ds")

        # service2 should not have the added datasource
        assert "instance1_ds" not in service2.list_datasources()
        assert "instance1_ds" in service1.list_datasources()
