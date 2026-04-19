"""
api/routers/scheduled_payments.py — Standing Orders & Direct Debits REST endpoints
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.scheduled_payments.direct_debit_engine import DirectDebitEngine
from services.scheduled_payments.failure_handler import FailureHandler
from services.scheduled_payments.models import PaymentFrequency
from services.scheduled_payments.schedule_executor import ScheduleExecutor
from services.scheduled_payments.scheduled_payments_agent import ScheduledPaymentsAgent
from services.scheduled_payments.standing_order_engine import StandingOrderEngine

router = APIRouter(tags=["scheduled_payments"])


@lru_cache(maxsize=1)
def _agent() -> ScheduledPaymentsAgent:
    return ScheduledPaymentsAgent()


@lru_cache(maxsize=1)
def _executor() -> ScheduleExecutor:
    return ScheduleExecutor()


@lru_cache(maxsize=1)
def _failure_handler() -> FailureHandler:
    return FailureHandler()


def _agent_dep() -> ScheduledPaymentsAgent:
    return _agent()


def _executor_dep() -> ScheduleExecutor:
    return _executor()


def _failure_dep() -> FailureHandler:
    return _failure_handler()


# ── POST /v1/standing-orders ───────────────────────────────────────────────────


@router.post("/v1/standing-orders", status_code=status.HTTP_201_CREATED)
def create_standing_order(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[ScheduledPaymentsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        end_date: datetime | None = None
        if body.get("end_date"):
            end_date = datetime.fromisoformat(body["end_date"])
        return agent.create_standing_order(
            customer_id=body["customer_id"],
            from_account=body["from_account"],
            to_account=body["to_account"],
            amount=Decimal(str(body["amount"])),
            frequency=PaymentFrequency(body["frequency"]),
            start_date=datetime.fromisoformat(body["start_date"]),
            end_date=end_date,
            reference=body.get("reference", ""),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── POST /v1/standing-orders/{so_id}/cancel ───────────────────────────────────


@router.post("/v1/standing-orders/{so_id}/cancel")
def cancel_standing_order(
    so_id: str,
    agent: Annotated[ScheduledPaymentsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        so_engine = StandingOrderEngine()
        return so_engine.cancel_standing_order(so_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── POST /v1/standing-orders/{so_id}/pause ────────────────────────────────────


@router.post("/v1/standing-orders/{so_id}/pause")
def pause_standing_order(
    so_id: str,
) -> dict[str, Any]:
    try:
        so_engine = StandingOrderEngine()
        return so_engine.pause_standing_order(so_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── POST /v1/standing-orders/{so_id}/resume ───────────────────────────────────


@router.post("/v1/standing-orders/{so_id}/resume")
def resume_standing_order(
    so_id: str,
) -> dict[str, Any]:
    try:
        so_engine = StandingOrderEngine()
        return so_engine.resume_standing_order(so_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── GET /v1/standing-orders/customers/{customer_id} ───────────────────────────


@router.get("/v1/standing-orders/customers/{customer_id}")
def list_standing_orders(
    customer_id: str,
) -> dict[str, Any]:
    so_engine = StandingOrderEngine()
    return so_engine.list_standing_orders(customer_id)


# ── POST /v1/direct-debits/mandate ────────────────────────────────────────────


@router.post("/v1/direct-debits/mandate", status_code=status.HTTP_201_CREATED)
def create_mandate(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[ScheduledPaymentsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    return agent.create_dd_mandate(
        customer_id=body["customer_id"],
        creditor_id=body["creditor_id"],
        creditor_name=body["creditor_name"],
        scheme_ref=body["scheme_ref"],
        service_user_number=body["service_user_number"],
    )


# ── POST /v1/direct-debits/mandate/{mandate_id}/authorise ─────────────────────


@router.post("/v1/direct-debits/mandate/{mandate_id}/authorise")
def authorise_mandate(
    mandate_id: str,
) -> dict[str, Any]:
    try:
        dd_engine = DirectDebitEngine()
        return dd_engine.authorise_mandate(mandate_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── POST /v1/direct-debits/mandate/{mandate_id}/cancel ────────────────────────


@router.post("/v1/direct-debits/mandate/{mandate_id}/cancel")
def cancel_mandate(
    mandate_id: str,
    agent: Annotated[ScheduledPaymentsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.cancel_mandate(mandate_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── GET /v1/scheduled-payments/{customer_id}/upcoming ─────────────────────────


@router.get("/v1/scheduled-payments/{customer_id}/upcoming")
def get_upcoming_payments(
    customer_id: str,
    days_ahead: int = 7,
    agent: Annotated[ScheduledPaymentsAgent, Depends(_agent_dep)] = None,
) -> dict[str, Any]:
    if agent is None:
        agent = _agent()
    return agent.get_upcoming_payments(customer_id, days_ahead=days_ahead)


# ── GET /v1/scheduled-payments/{customer_id}/failures ─────────────────────────


@router.get("/v1/scheduled-payments/{customer_id}/failures")
def get_failure_report(
    customer_id: str,
    agent: Annotated[ScheduledPaymentsAgent, Depends(_agent_dep)] = None,
) -> dict[str, Any]:
    if agent is None:
        agent = _agent()
    return agent.get_failure_report(customer_id)
