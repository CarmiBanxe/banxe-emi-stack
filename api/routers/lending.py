"""
api/routers/lending.py — Lending & Credit Engine REST API
IL-LCE-01 | Phase 25 | banxe-emi-stack
from api.deps import require_auth

POST   /v1/lending/apply                     — apply for a loan (202 HITL_REQUIRED, I-27)
GET    /v1/lending/products                  — list loan products
POST   /v1/lending/score                     — score a customer
GET    /v1/lending/products/{product_id}     — get product details
GET    /v1/lending/{application_id}          — get loan application
POST   /v1/lending/{application_id}/disburse — disburse approved loan
GET    /v1/lending/{application_id}/schedule — get repayment schedule
GET    /v1/lending/{application_id}/arrears  — get arrears history
POST   /v1/lending/{application_id}/payment  — process repayment
POST   /v1/lending/{application_id}/provision — compute ECL provision
from api.deps import require_auth

FCA compliance:
  - HITL gate for all credit decisions (I-27) → HTTP 202
  - All amounts as strings (I-05)
  - Decimal only, no float (I-01)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.lending.arrears_manager import ArrearsManager
from services.lending.credit_scorer import CreditScorer
from services.lending.lending_agent import LendingAgent
from services.lending.models import (
    IFRSStage,
    InMemoryLoanProductStore,
)
from services.lending.provisioning_engine import ProvisioningEngine
from services.lending.repayment_engine import RepaymentEngine

router = APIRouter(tags=["lending"])


# ── Factory ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> LendingAgent:
    return LendingAgent()


@lru_cache(maxsize=1)
def _get_scorer() -> CreditScorer:
    return CreditScorer()


@lru_cache(maxsize=1)
def _get_product_store() -> InMemoryLoanProductStore:
    return InMemoryLoanProductStore()


@lru_cache(maxsize=1)
def _get_repayment_engine() -> RepaymentEngine:
    return RepaymentEngine()


@lru_cache(maxsize=1)
def _get_arrears_manager() -> ArrearsManager:
    return ArrearsManager()


@lru_cache(maxsize=1)
def _get_provisioning_engine() -> ProvisioningEngine:
    return ProvisioningEngine()


# ── Request / Response models ──────────────────────────────────────────────


class LoanApplicationRequest(BaseModel):
    customer_id: str
    product_id: str
    requested_amount: str  # DecimalString (I-05)
    term_months: int


class DisburseRequest(BaseModel):
    actor: str = "compliance_officer"


class ScoreRequest(BaseModel):
    customer_id: str
    income: str  # DecimalString (I-05)
    account_age_months: int
    aml_risk_score: str  # DecimalString (I-05)


class PaymentRequest(BaseModel):
    amount: str  # DecimalString (I-05)


class ProvisionRequest(BaseModel):
    ifrs_stage: str  # STAGE_1 | STAGE_2 | STAGE_3
    exposure: str  # DecimalString (I-05)


class LoanApplicationResponse(BaseModel):
    application_id: str
    customer_id: str
    product_id: str
    requested_amount: str
    requested_term_months: int
    status: str
    applied_at: str
    decided_at: str | None = None
    decision_note: str = ""


class HITLRequiredResponse(BaseModel):
    status: str
    application_id: str
    credit_score: str
    outcome: str


class CreditScoreResponse(BaseModel):
    score_id: str
    customer_id: str
    score: str
    income_factor: str
    history_factor: str
    aml_risk_factor: str
    computed_at: str


class ProductResponse(BaseModel):
    product_id: str
    name: str
    product_type: str
    max_amount: str
    interest_rate: str
    max_term_months: int
    min_credit_score: str
    created_at: str


# ── Endpoints — fixed paths first, then parameterised ─────────────────────


@router.get("/v1/lending/products", response_model=list[ProductResponse])
def list_loan_products() -> list[ProductResponse]:
    """List all available loan products."""
    store = _get_product_store()
    return [
        ProductResponse(
            product_id=p.product_id,
            name=p.name,
            product_type=p.product_type.value,
            max_amount=str(p.max_amount),
            interest_rate=str(p.interest_rate),
            max_term_months=p.max_term_months,
            min_credit_score=str(p.min_credit_score),
            created_at=p.created_at.isoformat(),
        )
        for p in store.list_products()
    ]


@router.post("/v1/lending/apply", status_code=202, response_model=HITLRequiredResponse)
def apply_for_loan(req: LoanApplicationRequest) -> HITLRequiredResponse:
    """Apply for a loan — always returns 202 HITL_REQUIRED (FCA CONC, I-27)."""
    try:
        Decimal(req.requested_amount)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid amount: {req.requested_amount}"
        ) from exc

    agent = _get_agent()
    try:
        result = agent.apply_for_loan(
            customer_id=req.customer_id,
            product_id=req.product_id,
            requested_amount_str=req.requested_amount,
            term_months=req.term_months,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return HITLRequiredResponse(
        status=result["status"],
        application_id=result["application_id"],
        credit_score=result["credit_score"],
        outcome=result["outcome"],
    )


@router.post("/v1/lending/score", response_model=CreditScoreResponse)
def score_customer(req: ScoreRequest) -> CreditScoreResponse:
    """Score a customer's creditworthiness (0-1000 scale)."""
    try:
        income = Decimal(req.income)
        aml_risk = Decimal(req.aml_risk_score)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail=f"Invalid decimal value: {exc}") from exc

    scorer = _get_scorer()
    score = scorer.score_customer(
        customer_id=req.customer_id,
        income=income,
        account_age_months=req.account_age_months,
        aml_risk_score=aml_risk,
    )
    return CreditScoreResponse(
        score_id=score.score_id,
        customer_id=score.customer_id,
        score=str(score.score),
        income_factor=str(score.income_factor),
        history_factor=str(score.history_factor),
        aml_risk_factor=str(score.aml_risk_factor),
        computed_at=score.computed_at.isoformat(),
    )


@router.get("/v1/lending/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: str) -> ProductResponse:
    """Get a specific loan product by ID."""
    store = _get_product_store()
    product = store.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
    return ProductResponse(
        product_id=product.product_id,
        name=product.name,
        product_type=product.product_type.value,
        max_amount=str(product.max_amount),
        interest_rate=str(product.interest_rate),
        max_term_months=product.max_term_months,
        min_credit_score=str(product.min_credit_score),
        created_at=product.created_at.isoformat(),
    )


@router.get("/v1/lending/{application_id}", response_model=LoanApplicationResponse)
def get_application(application_id: str) -> LoanApplicationResponse:
    """Get a loan application by ID."""
    agent = _get_agent()
    app = agent._originator.get_application(application_id)
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application not found: {application_id}")
    return LoanApplicationResponse(
        application_id=app.application_id,
        customer_id=app.customer_id,
        product_id=app.product_id,
        requested_amount=str(app.requested_amount),
        requested_term_months=app.requested_term_months,
        status=app.status.value,
        applied_at=app.applied_at.isoformat(),
        decided_at=app.decided_at.isoformat() if app.decided_at else None,
        decision_note=app.decision_note,
    )


@router.post("/v1/lending/{application_id}/disburse", response_model=LoanApplicationResponse)
def disburse_loan(application_id: str, req: DisburseRequest) -> LoanApplicationResponse:
    """Disburse an approved loan (transitions APPROVED → DISBURSED)."""
    agent = _get_agent()
    try:
        app = agent._originator.disburse(application_id, actor=req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LoanApplicationResponse(
        application_id=app.application_id,
        customer_id=app.customer_id,
        product_id=app.product_id,
        requested_amount=str(app.requested_amount),
        requested_term_months=app.requested_term_months,
        status=app.status.value,
        applied_at=app.applied_at.isoformat(),
        decided_at=app.decided_at.isoformat() if app.decided_at else None,
        decision_note=app.decision_note,
    )


@router.get("/v1/lending/{application_id}/schedule")
def get_repayment_schedule(application_id: str) -> dict:
    """Get the repayment schedule for a loan application."""
    agent = _get_agent()
    result = agent.get_repayment_schedule(application_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/v1/lending/{application_id}/arrears")
def get_arrears_history(application_id: str) -> list[dict]:
    """Get arrears history for a loan application."""
    manager = _get_arrears_manager()
    records = manager.get_arrears_history(application_id)
    return [
        {
            "record_id": r.record_id,
            "application_id": r.application_id,
            "customer_id": r.customer_id,
            "stage": r.stage.value,
            "days_overdue": r.days_overdue,
            "outstanding_amount": str(r.outstanding_amount),
            "recorded_at": r.recorded_at.isoformat(),
        }
        for r in records
    ]


@router.post("/v1/lending/{application_id}/payment")
def process_payment(application_id: str, req: PaymentRequest) -> dict:
    """Process a loan repayment."""
    try:
        amount = Decimal(req.amount)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail=f"Invalid amount: {req.amount}") from exc

    engine = _get_repayment_engine()
    return engine.process_payment(application_id=application_id, amount=amount)


@router.post("/v1/lending/{application_id}/provision")
def compute_provision(application_id: str, req: ProvisionRequest) -> dict:
    """Compute IFRS 9 ECL provision for a loan exposure."""
    try:
        ifrs_stage = IFRSStage(req.ifrs_stage)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid IFRS stage: {req.ifrs_stage}. Must be STAGE_1, STAGE_2, or STAGE_3",
        ) from exc

    try:
        exposure = Decimal(req.exposure)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid exposure amount: {req.exposure}"
        ) from exc

    engine = _get_provisioning_engine()
    record = engine.compute_ecl(
        application_id=application_id,
        ifrs_stage=ifrs_stage,
        exposure_at_default=exposure,
    )
    return {
        "record_id": record.record_id,
        "application_id": record.application_id,
        "ifrs_stage": record.ifrs_stage.value,
        "ecl_amount": str(record.ecl_amount),
        "probability_of_default": str(record.probability_of_default),
        "exposure_at_default": str(record.exposure_at_default),
        "computed_at": record.computed_at.isoformat(),
    }
