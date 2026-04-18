"""
api/routers/batch_payments.py — Batch Payment Processing REST endpoints
IL-BPP-01 | Phase 36 | banxe-emi-stack
9 endpoints under /v1/batch-payments/
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.batch_payments.batch_creator import BatchCreator
from services.batch_payments.models import FileFormat, PaymentRail
from services.batch_payments.payment_dispatcher import PaymentDispatcher
from services.batch_payments.reconciliation_engine import BatchReconciliationEngine

router = APIRouter(tags=["batch_payments"])


@lru_cache(maxsize=1)
def _batch_creator() -> BatchCreator:
    return BatchCreator()


@lru_cache(maxsize=1)
def _dispatcher() -> PaymentDispatcher:
    return PaymentDispatcher()


@lru_cache(maxsize=1)
def _reconciler() -> BatchReconciliationEngine:
    return BatchReconciliationEngine()


def _bc_dep() -> BatchCreator:
    return _batch_creator()


def _dp_dep() -> PaymentDispatcher:
    return _dispatcher()


def _rc_dep() -> BatchReconciliationEngine:
    return _reconciler()


# ── POST /v1/batch-payments/ ──────────────────────────────────────────────────


@router.post("/v1/batch-payments/", status_code=status.HTTP_201_CREATED)
def create_batch(
    body: Annotated[dict[str, Any], Body()],
    bc: Annotated[BatchCreator, Depends(_bc_dep)],
) -> dict[str, Any]:
    try:
        rail = PaymentRail(body["rail"])
        file_format = FileFormat(body["file_format"])
        batch = bc.create_batch(
            name=body["name"],
            rail=rail,
            file_format=file_format,
            created_by=body["created_by"],
        )
        return {
            "id": batch.id,
            "name": batch.name,
            "status": batch.status.value,
            "rail": batch.rail.value,
            "file_format": batch.file_format.value,
            "total_amount": str(batch.total_amount),
            "item_count": batch.item_count,
            "created_by": batch.created_by,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/batch-payments/{batch_id}/items ──────────────────────────────────


@router.post("/v1/batch-payments/{batch_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(
    batch_id: str,
    body: Annotated[dict[str, Any], Body()],
    bc: Annotated[BatchCreator, Depends(_bc_dep)],
) -> dict[str, Any]:
    try:
        amount = Decimal(str(body["amount"]))
        item = bc.add_item(
            batch_id=batch_id,
            ref=body["ref"],
            beneficiary_iban=body["beneficiary_iban"],
            beneficiary_name=body["beneficiary_name"],
            amount=amount,
            currency=body.get("currency", "GBP"),
        )
        return {
            "id": item.id,
            "batch_id": item.batch_id,
            "ref": item.ref,
            "beneficiary_iban": item.beneficiary_iban,
            "amount": str(item.amount),
            "status": item.status.value,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/batch-payments/{batch_id}/validate ───────────────────────────────


@router.post("/v1/batch-payments/{batch_id}/validate")
def validate_batch(
    batch_id: str,
    bc: Annotated[BatchCreator, Depends(_bc_dep)],
) -> dict[str, Any]:
    try:
        result = bc.validate_all(batch_id)
        return {
            "batch_id": result.batch_id,
            "is_valid": result.is_valid,
            "errors": [e.value for e in result.errors],
            "warnings": result.warnings,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/batch-payments/{batch_id}/submit ─────────────────────────────────


@router.post("/v1/batch-payments/{batch_id}/submit")
def submit_batch(
    batch_id: str,
    bc: Annotated[BatchCreator, Depends(_bc_dep)],
) -> dict[str, Any]:
    try:
        proposal = bc.submit_batch(batch_id)
        return {
            "hitl_required": True,
            "action": proposal.action,
            "resource_id": proposal.resource_id,
            "requires_approval_from": proposal.requires_approval_from,
            "reason": proposal.reason,
            "autonomy_level": proposal.autonomy_level,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/batch-payments/{batch_id} ─────────────────────────────────────────


@router.get("/v1/batch-payments/{batch_id}")
def get_batch(
    batch_id: str,
    bc: Annotated[BatchCreator, Depends(_bc_dep)],
) -> dict[str, Any]:
    try:
        return bc.get_batch_summary(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/batch-payments/{batch_id}/items ───────────────────────────────────


@router.get("/v1/batch-payments/{batch_id}/items")
def list_items(
    batch_id: str,
    dp: Annotated[PaymentDispatcher, Depends(_dp_dep)],
) -> dict[str, Any]:
    items = dp._items.get_items(batch_id)  # type: ignore[attr-defined]
    return {
        "batch_id": batch_id,
        "items": [
            {
                "id": i.id,
                "ref": i.ref,
                "beneficiary_iban": i.beneficiary_iban,
                "amount": str(i.amount),
                "status": i.status.value,
            }
            for i in items
        ],
    }


# ── POST /v1/batch-payments/{batch_id}/dispatch ───────────────────────────────


@router.post("/v1/batch-payments/{batch_id}/dispatch")
def dispatch_batch(
    batch_id: str,
    dp: Annotated[PaymentDispatcher, Depends(_dp_dep)],
) -> dict[str, Any]:
    try:
        result = dp.dispatch_batch(batch_id)
        return {
            "batch_id": result.batch_id,
            "dispatched": result.dispatched,
            "failed": result.failed,
            "rail": result.rail.value,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/batch-payments/{batch_id}/status ─────────────────────────────────


@router.get("/v1/batch-payments/{batch_id}/status")
def get_status(
    batch_id: str,
    dp: Annotated[PaymentDispatcher, Depends(_dp_dep)],
) -> dict[str, Any]:
    return dp.get_dispatch_status(batch_id)


# ── GET /v1/batch-payments/{batch_id}/reconciliation ─────────────────────────


@router.get("/v1/batch-payments/{batch_id}/reconciliation")
def get_reconciliation_report(
    batch_id: str,
    rc: Annotated[BatchReconciliationEngine, Depends(_rc_dep)],
) -> dict[str, Any]:
    try:
        report = rc.generate_report(batch_id)
        return {
            "batch_id": report.batch_id,
            "total_items": report.total_items,
            "matched": report.matched,
            "partial": report.partial,
            "failed": report.failed,
            "discrepancy_amount": str(report.discrepancy_amount),
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
