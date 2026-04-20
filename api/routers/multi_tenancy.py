"""
api/routers/multi_tenancy.py — Multi-Tenancy REST endpoints
IL-MT-01 | Phase 43 | banxe-emi-stack
10 endpoints under /v1/tenants/
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.multi_tenancy.billing_engine import TenantBillingEngine
from services.multi_tenancy.quota_enforcer import QuotaEnforcer
from services.multi_tenancy.tenant_manager import TenantManager

router = APIRouter(tags=["multi_tenancy"])


@lru_cache(maxsize=1)
def _manager() -> TenantManager:
    return TenantManager()


@lru_cache(maxsize=1)
def _enforcer() -> QuotaEnforcer:
    return QuotaEnforcer()


@lru_cache(maxsize=1)
def _billing() -> TenantBillingEngine:
    return TenantBillingEngine()


def _mgr_dep() -> TenantManager:
    return _manager()


def _enf_dep() -> QuotaEnforcer:
    return _enforcer()


def _bil_dep() -> TenantBillingEngine:
    return _billing()


# ── POST /v1/tenants/ — provision (HITLProposal) ─────────────────────────────


@router.post("/v1/tenants/", status_code=status.HTTP_202_ACCEPTED)
def provision_tenant(
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    try:
        proposal = mgr.provision_tenant(
            name=body["name"],
            tier=body["tier"],
            jurisdiction=body["jurisdiction"],
            kyb_docs=body.get("kyb_docs", []),
        )
        return {
            "action": proposal.action,
            "tenant_id": proposal.tenant_id,
            "requires_approval_from": proposal.requires_approval_from,
            "reason": proposal.reason,
            "autonomy_level": proposal.autonomy_level,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing: {exc}"
        ) from exc


# ── GET /v1/tenants/ — list (admin only) ──────────────────────────────────────


@router.get("/v1/tenants/")
def list_tenants(
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
    filter_status: str | None = None,
) -> dict[str, Any]:
    tenants = mgr.list_tenants(status=filter_status)
    return {
        "tenants": [
            {
                "tenant_id": t.tenant_id,
                "name": t.name,
                "tier": t.tier.value,
                "status": t.status.value,
                "jurisdiction": t.jurisdiction,
                "monthly_fee": str(t.monthly_fee),
            }
            for t in tenants
        ]
    }


# ── GET /v1/tenants/{tenant_id} — get_tenant ─────────────────────────────────


@router.get("/v1/tenants/{tenant_id}")
def get_tenant(
    tenant_id: str,
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    tenant = mgr.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "tier": tenant.tier.value,
        "status": tenant.status.value,
        "isolation_level": tenant.isolation_level.value,
        "monthly_fee": str(tenant.monthly_fee),
        "daily_tx_limit": tenant.daily_tx_limit,
        "jurisdiction": tenant.jurisdiction,
        "kyb_verified": tenant.kyb_verified,
        "cass_pool_id": tenant.cass_pool_id,
    }


# ── POST /v1/tenants/{tenant_id}/activate ─────────────────────────────────────


@router.post("/v1/tenants/{tenant_id}/activate")
def activate_tenant(
    tenant_id: str,
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    try:
        tenant = mgr.activate_tenant(tenant_id, actor=body.get("actor", "system"))
        return {
            "tenant_id": tenant.tenant_id,
            "status": tenant.status.value,
            "cass_pool_id": tenant.cass_pool_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/tenants/{tenant_id}/suspend — HITLProposal ──────────────────────


@router.post("/v1/tenants/{tenant_id}/suspend", status_code=status.HTTP_202_ACCEPTED)
def suspend_tenant(
    tenant_id: str,
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    try:
        proposal = mgr.suspend_tenant(
            tenant_id, reason=body["reason"], actor=body.get("actor", "system")
        )
        return {
            "action": proposal.action,
            "tenant_id": proposal.tenant_id,
            "requires_approval_from": proposal.requires_approval_from,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/tenants/{tenant_id}/terminate — HITLProposal ─────────────────────


@router.post("/v1/tenants/{tenant_id}/terminate", status_code=status.HTTP_202_ACCEPTED)
def terminate_tenant(
    tenant_id: str,
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    try:
        proposal = mgr.terminate_tenant(
            tenant_id, reason=body["reason"], actor=body.get("actor", "system")
        )
        return {
            "action": proposal.action,
            "tenant_id": proposal.tenant_id,
            "requires_approval_from": proposal.requires_approval_from,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── PATCH /v1/tenants/{tenant_id}/tier — HITLProposal ────────────────────────


@router.patch("/v1/tenants/{tenant_id}/tier", status_code=status.HTTP_202_ACCEPTED)
def update_tier(
    tenant_id: str,
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    try:
        proposal = mgr.update_tier(
            tenant_id, new_tier=body["tier"], actor=body.get("actor", "system")
        )
        return {
            "action": proposal.action,
            "tenant_id": proposal.tenant_id,
            "requires_approval_from": proposal.requires_approval_from,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/tenants/{tenant_id}/verify-kyb ───────────────────────────────────


@router.post("/v1/tenants/{tenant_id}/verify-kyb")
def verify_kyb(
    tenant_id: str,
    body: Annotated[dict[str, Any], Body()],
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    try:
        tenant = mgr.verify_kyb(
            tenant_id,
            verification_ref=body["verification_ref"],
            actor=body.get("actor", "system"),
        )
        return {
            "tenant_id": tenant.tenant_id,
            "kyb_verified": tenant.kyb_verified,
            "status": tenant.status.value,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/tenants/{tenant_id}/quota ─────────────────────────────────────────


@router.get("/v1/tenants/{tenant_id}/quota")
def get_quota_status(
    tenant_id: str,
    enf: Annotated[QuotaEnforcer, Depends(_enf_dep)],
) -> dict[str, Any]:
    try:
        report = enf.get_quota_report(tenant_id)
        return report
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── GET /v1/tenants/{tenant_id}/audit-log ────────────────────────────────────


@router.get("/v1/tenants/{tenant_id}/audit-log")
def get_audit_log(
    tenant_id: str,
    mgr: Annotated[TenantManager, Depends(_mgr_dep)],
) -> dict[str, Any]:
    entries = mgr._audit.list_by_tenant(tenant_id)
    return {
        "tenant_id": tenant_id,
        "entries": [
            {
                "entry_id": e.entry_id,
                "action": e.action,
                "actor": e.actor,
                "timestamp": e.timestamp,
                "details": e.details,
            }
            for e in entries
        ],
    }
