"""
api/routers/dispute_resolution.py — Dispute Resolution & Chargeback REST endpoints
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.dispute_resolution.chargeback_bridge import ChargebackBridge
from services.dispute_resolution.dispute_agent import DisputeAgent
from services.dispute_resolution.models import (
    DisputeType,
    EscalationLevel,
    EvidenceType,
    ResolutionOutcome,
)

router = APIRouter(tags=["dispute_resolution"])


@lru_cache(maxsize=1)
def _agent() -> DisputeAgent:
    return DisputeAgent()


@lru_cache(maxsize=1)
def _chargeback() -> ChargebackBridge:
    return ChargebackBridge()


def _agent_dep() -> DisputeAgent:
    return _agent()


def _cb_dep() -> ChargebackBridge:
    return _chargeback()


# ── POST /v1/disputes ─────────────────────────────────────────────────────────


@router.post("/v1/disputes", status_code=status.HTTP_201_CREATED)
def file_dispute(
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[DisputeAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.open_dispute(
            customer_id=body["customer_id"],
            payment_id=body["payment_id"],
            dispute_type=DisputeType(body["dispute_type"]),
            amount=Decimal(str(body["amount"])),
            description=body.get("description", ""),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/disputes/{dispute_id} ─────────────────────────────────────────────


@router.get("/v1/disputes/{dispute_id}")
def get_dispute(
    dispute_id: str,
    agent: Annotated[DisputeAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        return agent.get_dispute_status(dispute_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/disputes/{dispute_id}/evidence ───────────────────────────────────


@router.post("/v1/disputes/{dispute_id}/evidence", status_code=status.HTTP_201_CREATED)
def submit_evidence(
    dispute_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[DisputeAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        file_content = (
            body.get("file_content", "").encode()
            if isinstance(body.get("file_content"), str)
            else b""
        )
        return agent.submit_evidence(
            dispute_id=dispute_id,
            evidence_type=EvidenceType(body["evidence_type"]),
            file_content=file_content,
            description=body.get("description", ""),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/disputes/{dispute_id}/resolve ────────────────────────────────────


@router.post("/v1/disputes/{dispute_id}/resolve")
def propose_resolution(
    dispute_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[DisputeAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    """Always returns HITL_REQUIRED (I-27, DISP 1.6)."""
    try:
        refund_amount = Decimal(str(body["refund_amount"])) if body.get("refund_amount") else None
        return agent.propose_resolution(
            dispute_id=dispute_id,
            outcome=ResolutionOutcome(body["outcome"]),
            refund_amount=refund_amount,
            reason=body.get("reason", ""),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/disputes/{dispute_id}/escalate ───────────────────────────────────


@router.post("/v1/disputes/{dispute_id}/escalate")
def escalate_dispute(
    dispute_id: str,
    body: Annotated[dict[str, Any], Body()],
    agent: Annotated[DisputeAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    try:
        level = EscalationLevel(body.get("level", EscalationLevel.LEVEL_1.value))
        return agent.escalate(
            dispute_id=dispute_id,
            reason=body.get("reason", ""),
            level=level,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/disputes/customers/{customer_id}/report ───────────────────────────


@router.get("/v1/disputes/customers/{customer_id}/report")
def get_resolution_report(
    customer_id: str,
    agent: Annotated[DisputeAgent, Depends(_agent_dep)],
) -> dict[str, Any]:
    return agent.get_resolution_report(customer_id)


# ── POST /v1/chargebacks ──────────────────────────────────────────────────────


@router.post("/v1/chargebacks", status_code=status.HTTP_201_CREATED)
def initiate_chargeback(
    body: Annotated[dict[str, Any], Body()],
    bridge: Annotated[ChargebackBridge, Depends(_cb_dep)],
) -> dict[str, Any]:
    try:
        return bridge.initiate_chargeback(
            dispute_id=body["dispute_id"],
            scheme=body["scheme"],
            amount=Decimal(str(body["amount"])),
            reason_code=body["reason_code"],
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/chargebacks/{chargeback_id} ───────────────────────────────────────


@router.get("/v1/chargebacks/{chargeback_id}")
def get_chargeback(
    chargeback_id: str,
    bridge: Annotated[ChargebackBridge, Depends(_cb_dep)],
) -> dict[str, Any]:
    try:
        return bridge.get_chargeback_status(chargeback_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/chargebacks/dispute/{dispute_id} ──────────────────────────────────


@router.get("/v1/chargebacks/dispute/{dispute_id}")
def list_chargebacks_for_dispute(
    dispute_id: str,
    bridge: Annotated[ChargebackBridge, Depends(_cb_dep)],
) -> dict[str, Any]:
    return bridge.list_chargebacks_for_dispute(dispute_id)
