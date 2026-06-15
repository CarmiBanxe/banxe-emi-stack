"""test_statement_port.py — contract tests for StatementPort (ADR-055).

These are light CONTRACT tests, not adapter/behaviour tests: StatementPort is a
pure abstract CONTRACT (bodies are `...`). They assert the contract shape —
StatementPort is an un-instantiable ABC, the four read/generate/deliver operations
are abstract, the value objects and enums are importable, money fields are Decimal
(never float) and identifiers are opaque (no raw PII) — and exercise the abstract
method bodies + error hierarchy for full file coverage.

Coverage note: `services/client_statements/statement_port.py` does NOT match the
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

from services.client_statements.statement_port import (
    ComplianceBlock,
    DeliveryChannel,
    DeliveryEgressBlocked,
    DeliveryResult,
    DeliveryStatus,
    GenerateStatementRequest,
    StatementDescriptor,
    StatementFormat,
    StatementNotFound,
    StatementPeriod,
    StatementPort,
    StatementPortError,
    StatementView,
)

_ABSTRACT_OPS = (
    "get_statement",
    "list_statements",
    "generate_statement",
    "deliver_statement",
)


# --------------------------------------------------------------------------- #
# Probe: a minimal concrete subclass that delegates to super() so the abstract
# `...` bodies execute (file coverage), while proving the ABC is implementable.
# --------------------------------------------------------------------------- #


class _Probe(StatementPort):
    async def get_statement(self, statement_id):  # type: ignore[override]
        return await super().get_statement(statement_id)

    async def list_statements(self, entity_id, period):  # type: ignore[override]
        return await super().list_statements(entity_id, period)

    async def generate_statement(self, request):  # type: ignore[override]
        return await super().generate_statement(request)

    async def deliver_statement(self, statement_id, channel):  # type: ignore[override]
        return await super().deliver_statement(statement_id, channel)


# --------------------------------------------------------------------------- #
# Pure-ABC shape
# --------------------------------------------------------------------------- #


def test_statement_port_is_abstract():
    """StatementPort is an ABC and cannot be instantiated directly."""
    assert issubclass(StatementPort, abc.ABC)
    with pytest.raises(TypeError):
        StatementPort()  # type: ignore[abstract]


def test_all_operations_are_abstract():
    """The four read/generate/deliver operations are declared @abstractmethod."""
    assert StatementPort.__abstractmethods__ == frozenset(_ABSTRACT_OPS)


def test_operations_are_async():
    """Every governed operation is an async coroutine function."""
    for name in _ABSTRACT_OPS:
        assert inspect.iscoroutinefunction(getattr(StatementPort, name))


# --------------------------------------------------------------------------- #
# Money is Decimal, never float  (I-01)
# --------------------------------------------------------------------------- #


def test_statement_view_money_is_decimal():
    view = StatementView(
        statement_id="stmt-1",
        entity_id="ent-1",
        period=StatementPeriod.MONTH,
        opening_balance=Decimal("100.00"),
        closing_balance=Decimal("250.50"),
        line_count=12,
        currency="GBP",
    )
    assert isinstance(view.opening_balance, Decimal)
    assert isinstance(view.closing_balance, Decimal)
    assert not isinstance(view.opening_balance, float)
    assert not isinstance(view.closing_balance, float)


# --------------------------------------------------------------------------- #
# Value objects + enums are importable and frozen
# --------------------------------------------------------------------------- #


def test_value_objects_are_frozen():
    view = StatementView(
        statement_id="stmt-1",
        entity_id="ent-1",
        period=StatementPeriod.YEAR,
        opening_balance=Decimal("0"),
        closing_balance=Decimal("0"),
        line_count=0,
        currency="GBP",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.closing_balance = Decimal("1")  # type: ignore[misc]


def test_enums_have_expected_members():
    assert {p.value for p in StatementPeriod} == {"MONTH", "QUARTER", "YEAR", "CUSTOM"}
    assert {f.value for f in StatementFormat} == {"PDF", "CSV", "JSON"}
    assert {c.value for c in DeliveryChannel} == {"IN_APP", "EMAIL", "EXPORT"}
    assert DeliveryStatus.PENDING_REVIEW in DeliveryStatus


def test_descriptor_request_and_result_types_construct():
    descriptor = StatementDescriptor(
        statement_id="stmt-1",
        period=StatementPeriod.QUARTER,
        currency="GBP",
    )
    request = GenerateStatementRequest(
        entity_id="ent-1",
        period=StatementPeriod.MONTH,
        format=StatementFormat.PDF,
        actor="agent-1",
        correlation_id="corr-1",
    )
    result = DeliveryResult(
        statement_id="stmt-1",
        channel=DeliveryChannel.IN_APP,
        status=DeliveryStatus.DELIVERED,
    )
    # PII default posture: egressed artefact redacted; descriptor not yet rendered.
    assert result.egress_redacted is True
    assert descriptor.format is None
    assert request.format is StatementFormat.PDF


# --------------------------------------------------------------------------- #
# Error taxonomy
# --------------------------------------------------------------------------- #


def test_error_hierarchy_and_correlation_id():
    for exc_cls in (StatementNotFound, DeliveryEgressBlocked, ComplianceBlock):
        assert issubclass(exc_cls, StatementPortError)
        err = exc_cls("boom", correlation_id="corr-9")
        assert err.correlation_id == "corr-9"
        assert str(err) == "boom"


def test_base_error_requires_keyword_correlation_id():
    with pytest.raises(TypeError):
        StatementPortError("boom")  # type: ignore[call-arg]  # correlation_id is keyword-only


# --------------------------------------------------------------------------- #
# Abstract bodies execute via super() (file coverage of the `...` statements)
# --------------------------------------------------------------------------- #


async def test_probe_super_delegation_covers_abstract_bodies():
    probe = _Probe()
    assert await probe.get_statement("stmt-1") is None
    assert await probe.list_statements("ent-1", StatementPeriod.MONTH) is None
    request = GenerateStatementRequest(
        entity_id="ent-1",
        period=StatementPeriod.MONTH,
        format=StatementFormat.JSON,
        actor="agent-1",
        correlation_id="corr-1",
    )
    assert await probe.generate_statement(request) is None
    assert await probe.deliver_statement("stmt-1", DeliveryChannel.IN_APP) is None
