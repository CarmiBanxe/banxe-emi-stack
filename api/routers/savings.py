"""
api/routers/savings.py — Savings & Interest Engine REST endpoints
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.savings.interest_calculator import InterestCalculator
from services.savings.rate_manager import RateManager
from services.savings.savings_agent import SavingsAgent

router = APIRouter(tags=["savings"])


@lru_cache(maxsize=1)
def _agent() -> SavingsAgent:
    return SavingsAgent()


@lru_cache(maxsize=1)
def _rate_manager() -> RateManager:
    return RateManager()


@lru_cache(maxsize=1)
def _calculator() -> InterestCalculator:
    return InterestCalculator()


def _agent_dep() -> SavingsAgent:
    return _agent()


def _rate_dep() -> RateManager:
    return _rate_manager()


def _calc_dep() -> InterestCalculator:
    return _calculator()


# ── POST /v1/savings/open ──────────────────────────────────────────────────────


@router.post("/v1/savings/open", status_code=status.HTTP_201_CREATED)
def open_account(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.open_account(
            customer_id=body["customer_id"],
            product_id=body["product_id"],
            initial_deposit=Decimal(str(body["initial_deposit"])),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── POST /v1/savings/{account_id}/deposit ─────────────────────────────────────


@router.post("/v1/savings/{account_id}/deposit")
def deposit(
    account_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.deposit(account_id, Decimal(str(body["amount"])))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── POST /v1/savings/{account_id}/withdraw ────────────────────────────────────


@router.post("/v1/savings/{account_id}/withdraw")
def withdraw(
    account_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.withdraw(account_id, Decimal(str(body["amount"])))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── GET /v1/savings/{account_id} ──────────────────────────────────────────────


@router.get("/v1/savings/{account_id}")
def get_account(
    account_id: str,
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.get_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/savings/{account_id}/interest ─────────────────────────────────────


@router.get("/v1/savings/{account_id}/interest")
def get_interest_summary(
    account_id: str,
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.get_interest_summary(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/savings/customers/{customer_id}/accounts ──────────────────────────


@router.get("/v1/savings/customers/{customer_id}/accounts")
def list_accounts(
    customer_id: str,
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    return agent.list_accounts(customer_id)


# ── GET /v1/savings/products ───────────────────────────────────────────────────


@router.get("/v1/savings/products")
def list_products(
    agent: Annotated[SavingsAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    from services.savings.product_catalog import ProductCatalog

    catalog = ProductCatalog()
    products = catalog.list_products()
    return {
        "count": len(products),
        "products": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "account_type": p.account_type.value,
                "gross_rate": str(p.gross_rate),
                "aer": str(p.aer),
                "min_deposit": str(p.min_deposit),
                "max_deposit": str(p.max_deposit),
                "tax_free": p.tax_free,
                "is_active": p.is_active,
            }
            for p in products
        ],
    }


# ── GET /v1/savings/rates/{product_id} ────────────────────────────────────────


@router.get("/v1/savings/rates/{product_id}")
def get_current_rate(
    product_id: str,
    rate_manager: Annotated[RateManager, Depends(_rate_dep)],
) -> dict[str, Any]:
    try:
        return rate_manager.get_current_rate(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/savings/rates/{product_id}/set ───────────────────────────────────


@router.post("/v1/savings/rates/{product_id}/set")
def set_rate(
    product_id: str,
    body: Annotated[dict[str, Any], Body()],
    rate_manager: Annotated[RateManager, Depends(_rate_dep)],
) -> dict[str, Any]:
    return rate_manager.set_rate(product_id, Decimal(str(body["gross_rate"])))


# ── POST /v1/savings/calculate-maturity ───────────────────────────────────────


@router.post("/v1/savings/calculate-maturity")
def calculate_maturity(
    body: Annotated[dict[str, Any], Body()],
    calculator: Annotated[InterestCalculator, Depends(_calc_dep)],
) -> dict[str, Any]:
    principal = Decimal(str(body["principal"]))
    gross_rate = Decimal(str(body["gross_rate"]))
    days = int(body["days"])
    maturity_amount = calculator.calculate_maturity_amount(principal, gross_rate, days)
    gross_interest = maturity_amount - principal
    tax_info = calculator.apply_tax_withholding(gross_interest)
    return {
        "principal": str(principal),
        "gross_rate": str(gross_rate),
        "days": days,
        "maturity_amount": str(maturity_amount),
        "gross_interest": str(gross_interest),
        "net_interest": tax_info["net_interest"],
        "tax_withheld": tax_info["tax_withheld"],
    }
