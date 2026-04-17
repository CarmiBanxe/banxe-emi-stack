"""
api/routers/beneficiary.py — Beneficiary & Payee Management REST endpoints
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.beneficiary_management.beneficiary_agent import BeneficiaryAgent
from services.beneficiary_management.models import BeneficiaryType

router = APIRouter(tags=["beneficiary"])


@lru_cache(maxsize=1)
def _agent() -> BeneficiaryAgent:
    return BeneficiaryAgent()


def _agent_dep() -> BeneficiaryAgent:
    return _agent()


# ── POST /v1/beneficiaries ────────────────────────────────────────────────────


@router.post("/v1/beneficiaries", status_code=status.HTTP_201_CREATED)
def add_beneficiary(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.add_beneficiary(
            customer_id=body["customer_id"],
            beneficiary_type=BeneficiaryType(body["beneficiary_type"]),
            name=body["name"],
            account_number=body.get("account_number", ""),
            sort_code=body.get("sort_code", ""),
            iban=body.get("iban", ""),
            bic=body.get("bic", ""),
            currency=body.get("currency", "GBP"),
            country_code=body.get("country_code", "GB"),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/beneficiaries/{beneficiary_id} ───────────────────────────────────


@router.get("/v1/beneficiaries/{beneficiary_id}")
def get_beneficiary(
    beneficiary_id: str,
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent._registry.get_beneficiary(beneficiary_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── DELETE /v1/beneficiaries/{beneficiary_id} ────────────────────────────────


@router.delete("/v1/beneficiaries/{beneficiary_id}")
def delete_beneficiary(
    beneficiary_id: str,
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    """Always returns HITL_REQUIRED (I-27)."""
    try:
        return agent.delete_beneficiary(beneficiary_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/beneficiaries/{beneficiary_id}/screen ───────────────────────────


@router.post("/v1/beneficiaries/{beneficiary_id}/screen")
def screen_beneficiary(
    beneficiary_id: str,
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.screen_beneficiary(beneficiary_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/beneficiaries/{beneficiary_id}/cop ──────────────────────────────


@router.post("/v1/beneficiaries/{beneficiary_id}/cop")
def check_payee(
    beneficiary_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.check_payee(beneficiary_id, body["expected_name"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/beneficiaries/customers/{customer_id} ────────────────────────────


@router.get("/v1/beneficiaries/customers/{customer_id}")
def list_beneficiaries(
    customer_id: str,
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    return agent.list_beneficiaries(customer_id)


# ── POST /v1/beneficiaries/{beneficiary_id}/route ────────────────────────────


@router.post("/v1/beneficiaries/{beneficiary_id}/route")
def route_payment(
    beneficiary_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.route_payment(
            beneficiary_id=beneficiary_id,
            amount=Decimal(str(body["amount"])),
            currency=body.get("currency", "GBP"),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/payment-rails ─────────────────────────────────────────────────────


@router.get("/v1/payment-rails")
def list_payment_rails(
    agent: Annotated[BeneficiaryAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    return agent._router.list_rails()
