"""
api/routers/kyc.py — KYC Workflow endpoints
IL-046 | banxe-emi-stack

POST /v1/kyc/workflows              — start KYC/KYB workflow
GET  /v1/kyc/workflows/{id}         — get workflow status
POST /v1/kyc/workflows/{id}/documents — submit documents
POST /v1/kyc/workflows/{id}/approve-edd — MLRO approves EDD
POST /v1/kyc/workflows/{id}/reject  — reject workflow
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_kyc_service
from api.models.kyc import (
    ApproveEDDRequest,
    CreateKYCWorkflowRequest,
    KYCWorkflowResponse,
    RejectWorkflowRequest,
    SubmitDocumentsRequest,
)
from services.kyc.kyc_port import KYCWorkflowRequest as DomainKYCRequest
from services.kyc.mock_kyc_workflow import MockKYCWorkflow

router = APIRouter(tags=["KYC"])


def _result_to_response(result) -> KYCWorkflowResponse:  # type: ignore[return]
    return KYCWorkflowResponse(
        workflow_id=result.workflow_id,
        customer_id=result.customer_id,
        kyc_type=result.kyc_type,
        status=result.status,
        requires_human_review=result.requires_human_review,
        rejection_reason=result.rejection_reason,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post(
    "/kyc/workflows",
    response_model=KYCWorkflowResponse,
    status_code=201,
    summary="Start a KYC/KYB workflow",
)
def create_kyc_workflow(
    body: CreateKYCWorkflowRequest,
    svc: MockKYCWorkflow = Depends(get_kyc_service),
) -> KYCWorkflowResponse:
    """
    Initiates KYC (individual) or KYB (corporate) verification.
    FCA MLR 2017 Reg.28: CDD before establishing business relationship.
    """
    domain_req = DomainKYCRequest(
        customer_id=body.customer_id,
        kyc_type=body.kyc_type,
        first_name="",  # Fetched from customer profile in full impl
        last_name="",
        date_of_birth="",
        nationality="GB",
        country_of_residence="GB",
        expected_transaction_volume=Decimal("0"),
    )
    result = svc.create_workflow(domain_req)
    return _result_to_response(result)


@router.get(
    "/kyc/workflows/{workflow_id}",
    response_model=KYCWorkflowResponse,
    summary="Get KYC workflow status",
)
def get_kyc_workflow(
    workflow_id: str,
    svc: MockKYCWorkflow = Depends(get_kyc_service),
) -> KYCWorkflowResponse:
    result = svc.get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return _result_to_response(result)


@router.post(
    "/kyc/workflows/{workflow_id}/documents",
    response_model=KYCWorkflowResponse,
    summary="Submit KYC documents",
)
def submit_documents(
    workflow_id: str,
    body: SubmitDocumentsRequest,
    svc: MockKYCWorkflow = Depends(get_kyc_service),
) -> KYCWorkflowResponse:
    result = svc.get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    if result.is_terminal:
        raise HTTPException(status_code=422, detail="Workflow is in a terminal state")
    updated = svc.submit_documents(workflow_id, body.document_ids)
    return _result_to_response(updated)


@router.post(
    "/kyc/workflows/{workflow_id}/approve-edd",
    response_model=KYCWorkflowResponse,
    summary="MLRO approves Enhanced Due Diligence",
)
def approve_edd(
    workflow_id: str,
    body: ApproveEDDRequest,
    svc: MockKYCWorkflow = Depends(get_kyc_service),
) -> KYCWorkflowResponse:
    """
    MLRO approves EDD. Only valid when workflow status is EDD_REQUIRED or MLRO_REVIEW.
    FCA MLR 2017 Reg.33: enhanced due diligence for high-risk customers.
    """
    result = svc.get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    updated = svc.approve_edd(workflow_id, body.mlro_user_id)
    return _result_to_response(updated)


@router.post(
    "/kyc/workflows/{workflow_id}/reject",
    response_model=KYCWorkflowResponse,
    summary="Reject KYC workflow",
)
def reject_workflow(
    workflow_id: str,
    body: RejectWorkflowRequest,
    svc: MockKYCWorkflow = Depends(get_kyc_service),
) -> KYCWorkflowResponse:
    result = svc.get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    if result.is_terminal:
        raise HTTPException(status_code=422, detail="Workflow is already in a terminal state")
    updated = svc.reject_workflow(workflow_id, body.reason)
    return _result_to_response(updated)
