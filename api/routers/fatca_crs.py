"""
api/routers/fatca_crs.py — FATCA/CRS Self-Certification endpoints
IL-FAT-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.fatca_crs.fatca_agent import FATCAAgent
from services.fatca_crs.fatca_models import CRSClassification, TaxResidency
from services.fatca_crs.self_cert_engine import SelfCertEngine

logger = logging.getLogger("banxe.fatca")
router = APIRouter(tags=["FATCA_CRS"])

_engine = SelfCertEngine()
_agent = FATCAAgent()


class CreateCertRequest(BaseModel):
    customer_id: str
    tax_residencies: list[TaxResidency]
    us_person: bool
    crs_classification: CRSClassification = CRSClassification.INDIVIDUAL


class RenewRequest(BaseModel):
    officer: str
    reason: str


@router.post(
    "/fatca-crs/certifications", status_code=201, summary="Create FATCA/CRS self-certification"
)
async def create_certification(body: CreateCertRequest):  # type: ignore[return]
    try:
        cert = _engine.create_cert(
            customer_id=body.customer_id,
            tax_residencies=body.tax_residencies,
            us_person=body.us_person,
            crs_classification=body.crs_classification,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "cert_id": cert.cert_id,
        "customer_id": cert.customer_id,
        "us_person": cert.us_person,
        "crs_classification": cert.crs_classification.value,
        "status": cert.status.value,
        "created_at": cert.created_at,
        "expires_at": cert.expires_at,
    }


@router.get("/fatca-crs/certifications/{customer_id}", summary="Get customer certifications")
async def get_certifications(customer_id: str):  # type: ignore[return]
    certs = _engine._store.get_by_customer(customer_id)
    return {
        "customer_id": customer_id,
        "certifications": [
            {"cert_id": c.cert_id, "status": c.status.value, "expires_at": c.expires_at}
            for c in certs
        ],
    }


@router.post("/fatca-crs/validate/{cert_id}", summary="Validate certification")
async def validate_cert(cert_id: str):  # type: ignore[return]
    result = _engine.validate_cert(cert_id)
    return {
        "cert_id": result.cert_id,
        "valid": result.valid,
        "errors": result.errors,
        "renewal_required": result.renewal_required,
    }


@router.get("/fatca-crs/renewals", summary="List certifications due for renewal")
async def list_renewals():  # type: ignore[return]
    certs = _engine.get_renewal_due()
    return {
        "renewal_count": len(certs),
        "certs": [
            {"cert_id": c.cert_id, "customer_id": c.customer_id, "expires_at": c.expires_at}
            for c in certs
        ],
    }


@router.post("/fatca-crs/renewals/{cert_id}/renew", summary="Trigger renewal (I-27 HITL L4)")
async def renew_certification(cert_id: str, body: RenewRequest):  # type: ignore[return]
    proposal = _agent.propose_us_person_change(cert_id, False)
    return {
        "status": "HITL_REQUIRED",
        "proposal_id": proposal.proposal_id,
        "requires_approval_from": proposal.requires_approval_from,
        "cert_id": cert_id,
    }
