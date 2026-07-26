"""tests/test_client_statements_adapter.py — StatementAdapter conformance tests.

Mirrors the 5 conformance tests documented in
services/client_statements/statement_port.py's StatementPort docstring.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.client_statements.statement_adapter import StatementAdapter
from services.client_statements.statement_port import (
    DeliveryChannel,
    DeliveryStatus,
    GenerateStatementRequest,
    StatementFormat,
    StatementNotFound,
    StatementPeriod,
    StatementPortError,
)


@pytest.fixture
def adapter() -> StatementAdapter:
    return StatementAdapter()


async def _generate(adapter: StatementAdapter, entity_id: str = "cust_1") -> str:
    request = GenerateStatementRequest(
        entity_id=entity_id,
        period=StatementPeriod.MONTH,
        format=StatementFormat.JSON,
        actor="test_actor",
        correlation_id="corr-1",
    )
    view = await adapter.generate_statement(request)
    return view.statement_id


async def test_conformance_1_get_statement_known_returns_view(adapter: StatementAdapter) -> None:
    statement_id = await _generate(adapter)
    view = await adapter.get_statement(statement_id)
    assert view.statement_id == statement_id
    assert view.entity_id == "cust_1"
    assert isinstance(view.opening_balance, Decimal)
    assert isinstance(view.closing_balance, Decimal)


async def test_conformance_1_get_statement_unknown_raises_not_found(
    adapter: StatementAdapter,
) -> None:
    with pytest.raises(StatementNotFound):
        await adapter.get_statement("unknown-id")


async def test_conformance_2_list_statements_read_only(adapter: StatementAdapter) -> None:
    statement_id = await _generate(adapter)
    listed = await adapter.list_statements("cust_1", StatementPeriod.MONTH)
    assert any(d.statement_id == statement_id for d in listed)
    # different entity sees nothing
    other = await adapter.list_statements("cust_2", StatementPeriod.MONTH)
    assert other == []


async def test_conformance_3_generate_statement_auto_within_cap(
    adapter: StatementAdapter,
) -> None:
    statement_id = await _generate(adapter)
    assert statement_id.startswith("stmt_")


async def test_generate_statement_custom_period_raises_port_error(
    adapter: StatementAdapter,
) -> None:
    request = GenerateStatementRequest(
        entity_id="cust_1",
        period=StatementPeriod.CUSTOM,
        format=StatementFormat.JSON,
        actor="test_actor",
        correlation_id="corr-2",
    )
    with pytest.raises(StatementPortError):
        await adapter.generate_statement(request)


async def test_conformance_4_deliver_statement_in_app_is_auto_delivered(
    adapter: StatementAdapter,
) -> None:
    statement_id = await _generate(adapter)
    result = await adapter.deliver_statement(statement_id, DeliveryChannel.IN_APP)
    assert result.status == DeliveryStatus.DELIVERED
    assert result.download_url == f"/files/statements/{statement_id}"


async def test_conformance_4_deliver_statement_external_channel_steps_to_review(
    adapter: StatementAdapter,
) -> None:
    statement_id = await _generate(adapter)
    for channel in (DeliveryChannel.EMAIL, DeliveryChannel.EXPORT):
        result = await adapter.deliver_statement(statement_id, channel)
        assert result.status == DeliveryStatus.PENDING_REVIEW
        assert result.download_url is None


async def test_deliver_statement_unknown_raises_not_found(adapter: StatementAdapter) -> None:
    with pytest.raises(StatementNotFound):
        await adapter.deliver_statement("unknown-id", DeliveryChannel.IN_APP)
