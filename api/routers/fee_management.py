"""
api/routers/fee_management.py
IL-FME-01 | Phase 41 | banxe-emi-stack

Fee Management REST API — 9 endpoints under /v1/fees/
I-01: All monetary amounts as strings (I-05).
FCA refs: PS21/3, BCOBS 5, PS22/9 §4 (Consumer Duty fee transparency).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.fee_management.billing_engine import BillingEngine
from services.fee_management.fee_agent import FeeAgent
from services.fee_management.fee_calculator import FeeCalculator
from services.fee_management.fee_reconciler import FeeReconciler
from services.fee_management.fee_transparency import FeeTransparency
from services.fee_management.models import (
    BillingCycle,
    InMemoryFeeChargeStore,
    InMemoryFeeRuleStore,
    InMemoryFeeWaiverStore,
    WaiverReason,
)
from services.fee_management.waiver_manager import WaiverManager

router = APIRouter(tags=["fee_management"])

# ── Shared stores (InMemory DI) ───────────────────────────────────────────────
_rule_store = InMemoryFeeRuleStore()
_charge_store = InMemoryFeeChargeStore()
_waiver_store = InMemoryFeeWaiverStore()

_calculator = FeeCalculator(rule_store=_rule_store, charge_store=_charge_store)
_billing = BillingEngine(rule_store=_rule_store, charge_store=_charge_store)
_waiver_mgr = WaiverManager(charge_store=_charge_store, waiver_store=_waiver_store)
_transparency = FeeTransparency(rule_store=_rule_store, calculator=_calculator)
_reconciler = FeeReconciler(rule_store=_rule_store, charge_store=_charge_store)
_agent = FeeAgent(rule_store=_rule_store, charge_store=_charge_store)


# ── Request / Response models ─────────────────────────────────────────────────


class EstimateRequest(BaseModel):
    transactions: int = 10
    avg_amount: str = "100.00"
    fx_volume: str = "0.00"
    tier: str = "STANDARD"


class ApplyChargeRequest(BaseModel):
    rule_id: str
    reference: str


class WaiverRequest(BaseModel):
    charge_id: str
    reason: str
    requested_by: str


def _rule_to_dict(rule: Any) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "fee_type": rule.fee_type.value,
        "category": rule.category.value,
        "amount": str(rule.amount),
        "percentage": str(rule.percentage) if rule.percentage is not None else None,
        "min_amount": str(rule.min_amount),
        "max_amount": str(rule.max_amount) if rule.max_amount is not None else None,
        "billing_cycle": rule.billing_cycle.value,
        "active": rule.active,
    }


def _charge_to_dict(charge: Any) -> dict:
    return {
        "id": charge.id,
        "rule_id": charge.rule_id,
        "account_id": charge.account_id,
        "amount": str(charge.amount),
        "status": charge.status.value,
        "description": charge.description,
        "reference": charge.reference,
        "applied_at": charge.applied_at.isoformat(),
        "paid_at": charge.paid_at.isoformat() if charge.paid_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/v1/fees/schedule")
async def get_fee_schedule() -> dict:
    """Return all active fee rules (public-facing)."""
    rules = _transparency.get_fee_schedule()
    return {"rules": [_rule_to_dict(r) for r in rules], "count": len(rules)}


@router.get("/v1/fees/schedule/compare")
async def compare_plans(plan_a: str, plan_b: str) -> dict:
    """Side-by-side comparison of two fee schedules."""
    return _transparency.compare_plans(plan_a, plan_b)


@router.post("/v1/fees/estimate")
async def estimate_fees(req: EstimateRequest) -> dict:
    """Estimate annual fee cost for given usage profile."""
    try:
        avg_amount = Decimal(req.avg_amount)
        fx_volume = Decimal(req.fx_volume)
    except InvalidOperation as e:
        raise HTTPException(status_code=422, detail=f"Invalid decimal value: {e}") from e
    annual = _transparency.estimate_annual_cost(
        transactions_per_month=req.transactions,
        avg_amount=avg_amount,
        fx_volume=fx_volume,
        tier=req.tier,
    )
    return {"tier": req.tier, "estimated_annual_cost": str(annual)}


@router.get("/v1/fees/accounts/{account_id}/charges")
async def list_charges(account_id: str) -> dict:
    """List all charges for an account."""
    charges = _billing.get_billing_history(account_id)
    return {"account_id": account_id, "charges": [_charge_to_dict(c) for c in charges]}


@router.post("/v1/fees/accounts/{account_id}/charges")
async def apply_charge(account_id: str, req: ApplyChargeRequest) -> dict:
    """Apply a fee charge to an account."""
    rule = _rule_store.get_rule(req.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {req.rule_id}")
    charges = _billing.apply_charges(account_id, [req.rule_id], req.reference)
    if not charges:
        raise HTTPException(status_code=400, detail="No charges created")
    return _charge_to_dict(charges[0])


@router.get("/v1/fees/accounts/{account_id}/outstanding")
async def get_outstanding(account_id: str) -> dict:
    """Return outstanding (PENDING) charges for an account."""
    charges = _billing.get_outstanding(account_id)
    return {"account_id": account_id, "outstanding": [_charge_to_dict(c) for c in charges]}


@router.post("/v1/fees/accounts/{account_id}/waivers")
async def request_waiver(account_id: str, req: WaiverRequest) -> dict:
    """Request a fee waiver — always returns HITLProposal (I-27)."""
    try:
        reason = WaiverReason(req.reason)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid waiver reason: {req.reason}") from e
    proposal = _waiver_mgr.request_waiver(
        charge_id=req.charge_id,
        account_id=account_id,
        reason=reason,
        requested_by=req.requested_by,
    )
    return {
        "action": proposal.action,
        "resource_id": proposal.resource_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


@router.get("/v1/fees/accounts/{account_id}/summary")
async def get_fee_summary(account_id: str) -> dict:
    """Generate fee summary for an account (current period)."""
    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    summary = _billing.generate_invoice(
        account_id=account_id,
        cycle=BillingCycle.MONTHLY,
        period_start=period_start,
        period_end=now,
    )
    return {
        "account_id": summary.account_id,
        "period_start": summary.period_start.isoformat(),
        "period_end": summary.period_end.isoformat(),
        "total_charged": str(summary.total_charged),
        "total_waived": str(summary.total_waived),
        "total_paid": str(summary.total_paid),
        "outstanding": str(summary.outstanding),
        "breakdown": {k: str(v) for k, v in summary.breakdown.items()},
    }


@router.post("/v1/fees/accounts/{account_id}/reconcile")
async def reconcile_account(account_id: str) -> dict:
    """Reconcile expected vs actual charges for account."""
    report = _reconciler.get_reconciliation_report(account_id)
    return {
        "account_id": report["account_id"],
        "total_charges": str(report["total_charges"]),
        "total_expected": str(report["total_expected"]),
        "discrepancy": str(report["discrepancy"]),
        "status": report["status"],
    }
