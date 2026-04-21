"""
api/routers/consumer_duty_v2.py — Consumer Duty Outcome Monitoring endpoints (Phase 50)
IL-CDO-01 | Phase 50 | Sprint 35

POST /v1/consumer-duty/outcomes               — assess outcome
GET  /v1/consumer-duty/outcomes/{customer_id} — get customer outcomes
GET  /v1/consumer-duty/outcomes/failing       — list failing outcomes
POST /v1/consumer-duty/vulnerability/detect   — detect vulnerability
PUT  /v1/consumer-duty/vulnerability/{cust}   — update flag (HITLProposal)
GET  /v1/consumer-duty/vulnerability/alerts   — unreviewed alerts
POST /v1/consumer-duty/products               — record product assessment
GET  /v1/consumer-duty/products/failing       — failing products
POST /v1/consumer-duty/products/{pid}/withdraw — withdraw product (HITLProposal)
GET  /v1/consumer-duty/dashboard              — outcome dashboard

FCA: PS22/9 Consumer Duty, FCA FG21/1, FCA PROD, FCA COBS 2.1, FCA PRIN 12
Trust Zone: AMBER
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from services.consumer_duty.consumer_duty_reporter import ConsumerDutyReporter
from services.consumer_duty.models_v2 import (
    HITLProposal,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
    OutcomeType,
    VulnerabilityFlag,
)
from services.consumer_duty.outcome_assessor import OutcomeAssessor
from services.consumer_duty.product_governance import ProductGovernanceService
from services.consumer_duty.vulnerability_detector import VulnerabilityDetector

router = APIRouter(tags=["Consumer Duty v2"])

# ── Shared stores ─────────────────────────────────────────────────────────────

_shared_outcome_store = InMemoryOutcomeStore()
_shared_governance_store = InMemoryProductGovernance()
_shared_alert_store = InMemoryVulnerabilityAlertStore()


@lru_cache(maxsize=1)
def _get_assessor() -> OutcomeAssessor:
    return OutcomeAssessor(_shared_outcome_store)


@lru_cache(maxsize=1)
def _get_detector() -> VulnerabilityDetector:
    return VulnerabilityDetector(_shared_alert_store)


@lru_cache(maxsize=1)
def _get_governance() -> ProductGovernanceService:
    return ProductGovernanceService(_shared_governance_store)


@lru_cache(maxsize=1)
def _get_reporter() -> ConsumerDutyReporter:
    return ConsumerDutyReporter(
        _shared_outcome_store,
        _shared_governance_store,
        _shared_alert_store,
    )


# ── Request models ────────────────────────────────────────────────────────────


class AssessOutcomeRequest(BaseModel):
    """Request to assess a PS22/9 outcome area."""

    customer_id: str
    outcome_type: OutcomeType
    evidence_data: dict[str, Any]


class DetectVulnerabilityRequest(BaseModel):
    """Request to detect vulnerability."""

    customer_id: str
    trigger: str
    context: dict[str, Any] = {}


class UpdateVulnerabilityRequest(BaseModel):
    """Request to update vulnerability flag."""

    vulnerability_flag: VulnerabilityFlag


class RecordProductRequest(BaseModel):
    """Request to record product governance assessment."""

    product_id: str
    product_name: str
    target_market: str
    fair_value_score: str  # Decimal string (I-01)
    evidence: str = ""

    @field_validator("fair_value_score")
    @classmethod
    def validate_score(cls, v: str) -> str:
        """Validate fair_value_score is valid Decimal 0.0–1.0."""
        try:
            d = Decimal(v)
            if not (Decimal("0.0") <= d <= Decimal("1.0")):
                raise ValueError("fair_value_score must be between 0.0 and 1.0")
        except Exception as exc:
            raise ValueError(f"Invalid fair_value_score: {exc}")
        return v


class WithdrawProductRequest(BaseModel):
    """Request to propose product withdrawal."""

    reason: str
    operator: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/consumer-duty/outcomes",
    status_code=201,
    summary="Assess PS22/9 outcome area for customer",
)
def assess_outcome(body: AssessOutcomeRequest) -> dict[str, Any]:
    """Assess a Consumer Duty outcome area for a customer.

    PS22/9: Firms must monitor and evidence good outcomes.
    Score < threshold → FAILED status.
    """
    assessor = _get_assessor()
    assessment = assessor.assess_outcome(
        customer_id=body.customer_id,
        outcome_type=body.outcome_type,
        evidence_data=body.evidence_data,
    )
    return {
        "assessment_id": assessment.assessment_id,
        "customer_id": assessment.customer_id,
        "outcome_type": assessment.outcome_type,
        "score": str(assessment.score),
        "status": assessment.status,
        "assessed_at": assessment.assessed_at,
        "evidence": assessment.evidence,
    }


@router.get(
    "/consumer-duty/outcomes/failing",
    summary="List failing outcome assessments",
)
def list_failing_outcomes(outcome_type: OutcomeType | None = None) -> list[dict[str, Any]]:
    """List all failing outcome assessments (score < threshold).

    PS22/9: Firms must take action on failing outcomes.
    """
    assessor = _get_assessor()
    failing = assessor.get_failing_outcomes(outcome_type)
    return [
        {
            "assessment_id": a.assessment_id,
            "customer_id": a.customer_id,
            "outcome_type": a.outcome_type,
            "score": str(a.score),
            "status": a.status,
            "assessed_at": a.assessed_at,
        }
        for a in failing
    ]


@router.get(
    "/consumer-duty/outcomes/{customer_id}",
    summary="Get outcome assessments for a customer",
)
def get_customer_outcomes(customer_id: str) -> list[dict[str, Any]]:
    """Get all outcome assessments for a customer.

    PS22/9: Customer-level outcome monitoring.
    """
    assessor = _get_assessor()
    assessments = assessor.get_customer_outcomes(customer_id)
    return [
        {
            "assessment_id": a.assessment_id,
            "customer_id": a.customer_id,
            "outcome_type": a.outcome_type,
            "score": str(a.score),
            "status": a.status,
            "assessed_at": a.assessed_at,
        }
        for a in assessments
    ]


@router.post(
    "/consumer-duty/vulnerability/detect",
    status_code=201,
    summary="Detect customer vulnerability trigger",
)
def detect_vulnerability(body: DetectVulnerabilityRequest) -> dict[str, Any]:
    """Detect and record customer vulnerability.

    FCA FG21/1: Firms must identify and respond to vulnerable customers.
    HIGH/CRITICAL returns HITLProposal (I-27).
    """
    detector = _get_detector()
    result = detector.detect_vulnerability(
        customer_id=body.customer_id,
        trigger=body.trigger,
        context=body.context,
    )
    if isinstance(result, HITLProposal):
        return {
            "type": "HITLProposal",
            "action": result.action,
            "entity_id": result.entity_id,
            "requires_approval_from": result.requires_approval_from,
            "reason": result.reason,
            "autonomy_level": result.autonomy_level,
        }
    return {
        "type": "VulnerabilityAlert",
        "alert_id": result.alert_id,
        "customer_id": result.customer_id,
        "vulnerability_flag": result.vulnerability_flag,
        "trigger": result.trigger,
        "created_at": result.created_at,
        "reviewed_by": result.reviewed_by,
    }


@router.put(
    "/consumer-duty/vulnerability/{customer_id}",
    summary="Update vulnerability flag — returns HITLProposal (I-27)",
)
def update_vulnerability_flag(customer_id: str, body: UpdateVulnerabilityRequest) -> dict[str, Any]:
    """Update customer vulnerability flag — always returns HITL proposal (I-27).

    FCA FG21/1 §2.8: Vulnerability classification changes require human oversight.
    """
    detector = _get_detector()
    proposal = detector.update_vulnerability_flag(customer_id, body.vulnerability_flag)
    return {
        "action": proposal.action,
        "entity_id": proposal.entity_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


@router.get(
    "/consumer-duty/vulnerability/alerts",
    summary="List unreviewed vulnerability alerts",
)
def list_vulnerability_alerts() -> list[dict[str, Any]]:
    """List all unreviewed vulnerability alerts.

    FCA FG21/1: Firms must act on identified vulnerability signals.
    """
    detector = _get_detector()
    alerts = detector.get_unreviewed_alerts()
    return [
        {
            "alert_id": a.alert_id,
            "customer_id": a.customer_id,
            "vulnerability_flag": a.vulnerability_flag,
            "trigger": a.trigger,
            "created_at": a.created_at,
            "reviewed_by": a.reviewed_by,
        }
        for a in alerts
    ]


@router.post(
    "/consumer-duty/products",
    status_code=201,
    summary="Record product governance assessment",
)
def record_product_assessment(body: RecordProductRequest) -> dict[str, Any]:
    """Record a product fair value assessment.

    FCA PROD: Firms must assess and document product governance.
    Score < 0.6 → RESTRICT intervention + HITLProposal (I-27).
    """
    governance = _get_governance()
    result = governance.record_product_assessment(
        product_id=body.product_id,
        product_name=body.product_name,
        target_market=body.target_market,
        fair_value_score=Decimal(body.fair_value_score),
        evidence=body.evidence,
    )
    if isinstance(result, HITLProposal):
        return {
            "type": "HITLProposal",
            "action": result.action,
            "entity_id": result.entity_id,
            "requires_approval_from": result.requires_approval_from,
            "reason": result.reason,
            "autonomy_level": result.autonomy_level,
        }
    return {
        "type": "ProductGovernanceRecord",
        "record_id": result.record_id,
        "product_id": result.product_id,
        "product_name": result.product_name,
        "fair_value_score": str(result.fair_value_score),
        "intervention_type": result.intervention_type,
        "last_review_at": result.last_review_at,
    }


@router.get(
    "/consumer-duty/products/failing",
    summary="List failing product governance records",
)
def list_failing_products() -> list[dict[str, Any]]:
    """List products with RESTRICT or WITHDRAW intervention.

    FCA PROD: Firms must take action on failing products.
    """
    governance = _get_governance()
    failing = governance.get_failing_products()
    return [
        {
            "record_id": r.record_id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "fair_value_score": str(r.fair_value_score),
            "intervention_type": r.intervention_type,
            "last_review_at": r.last_review_at,
        }
        for r in failing
    ]


@router.post(
    "/consumer-duty/products/{product_id}/withdraw",
    summary="Propose product withdrawal — returns HITLProposal (I-27)",
)
def withdraw_product(product_id: str, body: WithdrawProductRequest) -> dict[str, Any]:
    """Propose product withdrawal — always returns HITL proposal (I-27).

    FCA PROD: Product withdrawal requires human oversight.
    """
    governance = _get_governance()
    proposal = governance.propose_product_withdrawal(product_id, body.reason, body.operator)
    return {
        "action": proposal.action,
        "entity_id": proposal.entity_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


@router.get(
    "/consumer-duty/dashboard",
    summary="Consumer Duty outcome monitoring dashboard",
)
def get_outcome_dashboard() -> dict[str, Any]:
    """Get Consumer Duty outcome monitoring dashboard.

    PS22/9 §10: Firms must monitor and report on outcomes.
    Covers all 4 outcome areas, vulnerability counts, failing products.
    """
    reporter = _get_reporter()
    return reporter.generate_outcome_dashboard()
