"""
services/fx_exchange/fx_executor.py
IL-FX-01 | Phase 21

FXExecutor — creates and executes FX orders.
PENDING → EXECUTED transition with Decimal fee calculation.
BLOCKED compliance flag raises ValueError (hard stop).
Append-only audit trail for every state transition (I-24).
All monetary amounts are Decimal (I-01).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.fx_exchange.models import (
    ComplianceFlag,
    CurrencyPair,
    ExecutionStorePort,
    FXAuditPort,
    FXExecution,
    FXOrder,
    FXOrderStatus,
    FXOrderType,
    FXQuote,
    OrderStorePort,
)

_FX_FEE_RATE: Decimal = Decimal("0.001")  # 0.1% FX execution fee


class FXExecutor:
    """Creates and executes FX spot orders.

    Business rules:
    - BLOCKED compliance flag → ValueError (hard stop, no order created).
    - Only PENDING orders can be executed.
    - Fee = amount_base * 0.001 (Decimal multiplication, never float).
    - All transitions logged to FXAuditPort (I-24, append-only).
    """

    def __init__(
        self,
        order_store: OrderStorePort,
        execution_store: ExecutionStorePort,
        audit: FXAuditPort,
    ) -> None:
        self._orders = order_store
        self._executions = execution_store
        self._audit = audit

    async def create_order(
        self,
        entity_id: str,
        pair: CurrencyPair,
        amount_base: Decimal,
        quote: FXQuote,
        compliance_flag: ComplianceFlag,
    ) -> FXOrder:
        """Create a PENDING FX order.

        Raises:
            ValueError: if compliance_flag is BLOCKED.
        """
        if compliance_flag == ComplianceFlag.BLOCKED:
            raise ValueError(
                f"FX order blocked for entity {entity_id}: "
                f"currency pair {pair} contains a sanctioned currency."
            )

        amount_quote = amount_base * quote.rate
        order = FXOrder(
            order_id=str(uuid.uuid4()),
            entity_id=entity_id,
            pair=pair,
            amount_base=amount_base,
            amount_quote=amount_quote,
            rate=quote.rate,
            order_type=FXOrderType.SPOT,
            status=FXOrderStatus.PENDING,
            compliance_flag=compliance_flag,
            created_at=datetime.now(UTC),
        )
        await self._orders.save_order(order)
        await self._audit.log_event(
            "fx_order_created",
            {
                "entity_id": entity_id,
                "order_id": order.order_id,
                "pair": str(pair),
                "amount_base": str(amount_base),
                "compliance_flag": compliance_flag.value,
            },
        )
        return order

    async def execute_order(self, order_id: str) -> FXExecution:
        """Transition PENDING → EXECUTED and create FXExecution record.

        Fee = amount_base * 0.001 (0.1% FX fee, Decimal).
        Debit account = entity_id + "_" + pair.base
        Credit account = entity_id + "_" + pair.quote

        Raises:
            ValueError: if order not found or not in PENDING status.
        """
        order = await self._orders.get_order(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")
        if order.status != FXOrderStatus.PENDING:
            raise ValueError(f"Order {order_id} cannot be executed: status is {order.status.value}")

        fee = order.amount_base * _FX_FEE_RATE
        now = datetime.now(UTC)

        execution = FXExecution(
            execution_id=str(uuid.uuid4()),
            order_id=order_id,
            debit_account=f"{order.entity_id}_{order.pair.base}",
            credit_account=f"{order.entity_id}_{order.pair.quote}",
            debit_amount=order.amount_base,
            credit_amount=order.amount_quote,
            rate=order.rate,
            fee=fee,
            created_at=now,
        )
        await self._executions.save_execution(execution)

        # Transition order status (frozen dataclass → replace)
        executed_order = replace(order, status=FXOrderStatus.EXECUTED, executed_at=now)
        await self._orders.save_order(executed_order)

        await self._audit.log_event(
            "fx_order_executed",
            {
                "entity_id": order.entity_id,
                "order_id": order_id,
                "execution_id": execution.execution_id,
                "fee": str(fee),
                "rate": str(order.rate),
            },
        )
        return execution

    async def get_order(self, order_id: str) -> FXOrder | None:
        """Retrieve an order by ID."""
        return await self._orders.get_order(order_id)

    async def list_executions(self, entity_id: str) -> list[FXExecution]:
        """List all executions (filtered by entity via order lookup)."""
        all_executions = await self._executions.list_executions(entity_id)
        # Filter by entity_id via order cross-reference
        result: list[FXExecution] = []
        for execution in all_executions:
            order = await self._orders.get_order(execution.order_id)
            if order is not None and order.entity_id == entity_id:
                result.append(execution)
        return result
