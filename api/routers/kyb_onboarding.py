from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.kyb_onboarding.application_manager import ApplicationManager
from services.kyb_onboarding.kyb_agent import KYBAgent
from services.kyb_onboarding.models import (
    BusinessType,
    DocumentType,
    InMemoryApplicationStore,
    InMemoryKYBDecisionStore,
    InMemoryKYBDocumentStore,
    InMemoryUBOStore,
    KYBDocument,
    KYBStatus,
)
from services.kyb_onboarding.onboarding_workflow import OnboardingWorkflow
from services.kyb_onboarding.risk_assessor import KYBRiskAssessor
from services.kyb_onboarding.ubo_registry import UBORegistry

router = APIRouter()

# Singleton stores
_app_store = InMemoryApplicationStore()
_doc_store = InMemoryKYBDocumentStore()
_decision_store = InMemoryKYBDecisionStore()
_ubo_store = InMemoryUBOStore()

_manager = ApplicationManager(_app_store, _doc_store, _decision_store)
_ubo_registry = UBORegistry(_ubo_store)
_risk_assessor = KYBRiskAssessor(_app_store, _ubo_store)
_agent = KYBAgent(_app_store, _ubo_store, _doc_store)
_workflow = OnboardingWorkflow(_app_store)


class SubmitApplicationRequest(BaseModel):
    business_name: str
    business_type: str
    companies_house_number: str = ""
    jurisdiction: str


class DocumentUploadRequest(BaseModel):
    document_type: str
    file_hash: str


class UBORequest(BaseModel):
    full_name: str
    nationality: str
    date_of_birth: str
    ownership_pct: str
    is_psc: bool = False


class DecisionRequest(BaseModel):
    recommended_status: str
    reason: str


@router.post("/applications")
def submit_application(body: SubmitApplicationRequest) -> dict:
    try:
        btype = BusinessType(body.business_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid business_type: {body.business_type}")
    try:
        app = _manager.submit_application(
            body.business_name, btype, body.companies_house_number, body.jurisdiction
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "application_id": app.application_id,
        "status": app.status,
        "submitted_at": app.submitted_at,
    }


@router.get("/applications")
def list_applications(status: str | None = None) -> dict:
    st = KYBStatus(status) if status else None
    apps = _manager.list_applications(st)
    return {
        "applications": [
            {
                "application_id": a.application_id,
                "status": a.status,
                "business_name": a.business_name,
            }
            for a in apps
        ]
    }


@router.get("/applications/{application_id}")
def get_application(application_id: str) -> dict:
    app = _manager.get_application(application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        "application_id": app.application_id,
        "business_name": app.business_name,
        "business_type": app.business_type,
        "jurisdiction": app.jurisdiction,
        "status": app.status,
        "submitted_at": app.submitted_at,
    }


@router.post("/applications/{application_id}/documents")
def upload_document(application_id: str, body: DocumentUploadRequest) -> dict:
    try:
        dtype = DocumentType(body.document_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid document_type: {body.document_type}")
    ts = datetime.now(UTC).isoformat()
    doc_id = f"doc_{hashlib.sha256(f'{application_id}{dtype}{ts}'.encode()).hexdigest()[:8]}"
    doc = KYBDocument(doc_id, application_id, dtype, body.file_hash, ts)
    _doc_store.save(doc)
    return {"document_id": doc_id, "document_type": dtype, "uploaded_at": ts}


@router.post("/applications/{application_id}/ubos")
def register_ubo(application_id: str, body: UBORequest) -> dict:
    try:
        ubo = _ubo_registry.register_ubo(
            application_id,
            body.full_name,
            body.nationality,
            body.date_of_birth,
            Decimal(body.ownership_pct),
            body.is_psc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ubo_id": ubo.ubo_id, "verification_status": ubo.verification_status}


@router.get("/applications/{application_id}/ubos")
def list_ubos(application_id: str) -> dict:
    ubos = _ubo_registry.get_ubos_for_business(application_id)
    return {
        "ubos": [
            {"ubo_id": u.ubo_id, "full_name": u.full_name, "ownership_pct": str(u.ownership_pct)}
            for u in ubos
        ]
    }


@router.post("/applications/{application_id}/risk")
def run_risk_assessment(application_id: str) -> dict:
    try:
        assessment = _risk_assessor.assess_risk(application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "assessment_id": assessment.assessment_id,
        "risk_score": str(assessment.risk_score),
        "risk_tier": assessment.risk_tier,
        "factors": assessment.factors,
    }


@router.post("/applications/{application_id}/decision")
def request_decision(application_id: str, body: DecisionRequest) -> dict:
    try:
        status = KYBStatus(body.recommended_status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid recommended_status")
    proposal = _agent.process_decision(application_id, status, body.reason)
    return {
        "hitl_required": True,
        "action": proposal.action,
        "requires_approval_from": proposal.requires_approval_from,
        "autonomy_level": proposal.autonomy_level,
        "reason": proposal.reason,
    }


@router.get("/applications/{application_id}/workflow")
def get_workflow_status(application_id: str) -> dict:
    return _workflow.get_workflow_status(application_id)


@router.post("/applications/{application_id}/screen")
def screen_ubos(application_id: str) -> dict:
    result = _agent.process_ubo_screening(application_id)
    if isinstance(result, dict):
        return result
    return {
        "hitl_required": True,
        "action": result.action,
        "requires_approval_from": result.requires_approval_from,
        "reason": result.reason,
    }
