"""test_analytics_port.py — contract tests for AnalyticsPort (ADR-054 C7).

These are light CONTRACT tests, not adapter/behaviour tests: AnalyticsPort is a
pure abstract CONTRACT (bodies are `...`). They assert the contract shape —
AnalyticsPort is an un-instantiable ABC, the five read/report operations are
abstract, the value objects and enums are importable, money fields are Decimal
(never float) and entity references are opaque (no raw PII) — and exercise the
abstract method bodies + error hierarchy for full file coverage.

Coverage note: `services/reporting_analytics/analytics_port.py` does NOT match the
`services/*/*_provider_port.py` coverage omit glob (pyproject [tool.coverage.run]),
so the file IS measured. A `_Probe` subclass delegates each operation to
`super()` so the `...` bodies execute, giving 100% file coverage with no
pyproject change.
"""

from __future__ import annotations

import abc
import dataclasses
from decimal import Decimal
import inspect

import pytest

from services.reporting_analytics.analytics_port import (
    AnalyticsPort,
    AnalyticsPortError,
    ComplianceBlock,
    ExportRequest,
    ExportResult,
    ExportStatus,
    ExportTooLarge,
    PortfolioPosition,
    PortfolioView,
    ReportDescriptor,
    ReportFormat,
    ReportNotFound,
    ReportView,
    SpendingSummary,
    SpendPeriod,
)

_ABSTRACT_OPS = (
    "get_spending_summary",
    "get_portfolio_view",
    "get_report",
    "list_available_reports",
    "request_export",
)


# --------------------------------------------------------------------------- #
# Probe: a minimal concrete subclass that delegates to super() so the abstract
# `...` bodies execute (file coverage), while proving the ABC is implementable.
# --------------------------------------------------------------------------- #


class _Probe(AnalyticsPort):
    async def get_spending_summary(self, entity_id, period):  # type: ignore[override]
        return await super().get_spending_summary(entity_id, period)

    async def get_portfolio_view(self, entity_id):  # type: ignore[override]
        return await super().get_portfolio_view(entity_id)

    async def get_report(self, report_id):  # type: ignore[override]
        return await super().get_report(report_id)

    async def list_available_reports(self, entity_id):  # type: ignore[override]
        return await super().list_available_reports(entity_id)

    async def request_export(self, request):  # type: ignore[override]
        return await super().request_export(request)


# --------------------------------------------------------------------------- #
# Pure-ABC shape
# --------------------------------------------------------------------------- #


def test_analytics_port_is_abstract():
    """AnalyticsPort is an ABC and cannot be instantiated directly."""
    assert issubclass(AnalyticsPort, abc.ABC)
    with pytest.raises(TypeError):
        AnalyticsPort()  # type: ignore[abstract]


def test_all_operations_are_abstract():
    """The five read/report operations are declared @abstractmethod."""
    assert AnalyticsPort.__abstractmethods__ == frozenset(_ABSTRACT_OPS)


def test_operations_are_async():
    """Every governed operation is an async coroutine function."""
    for name in _ABSTRACT_OPS:
        assert inspect.iscoroutinefunction(getattr(AnalyticsPort, name))


# --------------------------------------------------------------------------- #
# Money is Decimal, never float  (I-01)
# --------------------------------------------------------------------------- #


def test_spending_summary_money_is_decimal():
    summary = SpendingSummary(
        entity_id="ent-1",
        period=SpendPeriod.MONTH,
        total=Decimal("100.50"),
        currency="EUR",
        by_category={"groceries": Decimal("40.50")},
    )
    assert isinstance(summary.total, Decimal)
    assert not isinstance(summary.total, float)
    assert all(isinstance(v, Decimal) for v in summary.by_category.values())


def test_portfolio_view_money_is_decimal():
    position = PortfolioPosition(
        asset="BTC",
        quantity=Decimal("0.5"),
        market_value=Decimal("20000.00"),
        currency="EUR",
    )
    view = PortfolioView(
        entity_id="ent-1",
        total_value=Decimal("20000.00"),
        currency="EUR",
        positions=[position],
    )
    assert isinstance(view.total_value, Decimal)
    assert isinstance(view.positions[0].market_value, Decimal)


# --------------------------------------------------------------------------- #
# Value objects + enums are importable and frozen
# --------------------------------------------------------------------------- #


def test_value_objects_are_frozen():
    summary = SpendingSummary(
        entity_id="ent-1",
        period=SpendPeriod.DAY,
        total=Decimal("0"),
        currency="EUR",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.total = Decimal("1")  # type: ignore[misc]


def test_enums_have_expected_members():
    assert {p.value for p in SpendPeriod} == {"DAY", "WEEK", "MONTH", "YEAR", "CUSTOM"}
    assert ExportStatus.PENDING_REVIEW in ExportStatus
    assert ReportFormat.JSON in ReportFormat


def test_report_and_export_types_construct():
    report = ReportView(
        report_id="r-1",
        entity_id="ent-1",
        title="Q1 spend",
        format=ReportFormat.PDF,
    )
    descriptor = ReportDescriptor(report_id="r-1", title="Q1 spend", format=ReportFormat.PDF)
    request = ExportRequest(
        entity_id="ent-1",
        report_id="r-1",
        format=ReportFormat.CSV,
        actor="agent-1",
        correlation_id="corr-1",
    )
    result = ExportResult(
        report_id="r-1",
        format=ReportFormat.CSV,
        status=ExportStatus.READY,
        size_bytes=10,
    )
    # PII default posture: redacted; export not requesting raw PII.
    assert result.pii_redacted is True
    assert request.include_pii is False
    assert report.rows == [] and descriptor.description == ""


# --------------------------------------------------------------------------- #
# Error taxonomy
# --------------------------------------------------------------------------- #


def test_error_hierarchy_and_correlation_id():
    for exc_cls in (ReportNotFound, ExportTooLarge, ComplianceBlock):
        assert issubclass(exc_cls, AnalyticsPortError)
        err = exc_cls("boom", correlation_id="corr-9")
        assert err.correlation_id == "corr-9"
        assert str(err) == "boom"


def test_base_error_requires_keyword_correlation_id():
    with pytest.raises(TypeError):
        AnalyticsPortError("boom")  # type: ignore[call-arg]  # correlation_id is keyword-only


# --------------------------------------------------------------------------- #
# Abstract bodies execute via super() (file coverage of the `...` statements)
# --------------------------------------------------------------------------- #


async def test_probe_super_delegation_covers_abstract_bodies():
    probe = _Probe()
    assert await probe.get_spending_summary("ent-1", SpendPeriod.MONTH) is None
    assert await probe.get_portfolio_view("ent-1") is None
    assert await probe.get_report("r-1") is None
    assert await probe.list_available_reports("ent-1") is None
    request = ExportRequest(
        entity_id="ent-1",
        report_id="r-1",
        format=ReportFormat.JSON,
        actor="agent-1",
        correlation_id="corr-1",
    )
    assert await probe.request_export(request) is None
