"""
api/routers/fraud.py — Fraud + AML Assessment endpoints
IL-049 | S9-05 | banxe-emi-stack

POST /v1/fraud/assess — pre-payment fraud and AML gate (operator/internal)

FCA compliance:
  - PSR APP 2024: APP scam detection mandatory gate
  - MLR 2017 Reg.28: EDD gate for high-value transactions
  - I-06: sanctions hard block
  - I-05: amounts as decimal strings, never float
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from fastapi import APIRouter

from api.models.fraud import FraudAssessRequest, FraudAssessResponse
from services.aml.tx_monitor import TxMonitorService
from services.fraud.fraud_aml_pipeline import FraudAMLPipeline, PipelineRequest
from services.fraud.mock_fraud_adapter import MockFraudAdapter

router = APIRouter(tags=["Fraud & AML"])


@lru_cache(maxsize=1)
def _get_pipeline() -> FraudAMLPipeline:
    """
    Default pipeline: MockFraudAdapter + TxMonitorService (InMemoryVelocityTracker).
    In production: swap adapters via env vars (FRAUD_ADAPTER=sardine,
    VelocityTracker=redis) by overriding this in deps.py.
    """
    fraud_adapter = MockFraudAdapter()
    monitor = TxMonitorService()
    return FraudAMLPipeline(fraud_adapter=fraud_adapter, tx_monitor=monitor)


@router.post(
    "/fraud/assess",
    response_model=FraudAssessResponse,
    status_code=200,
    summary="Assess transaction — Fraud + AML pre-payment gate",
)
def assess_transaction(
    body: FraudAssessRequest,
) -> FraudAssessResponse:
    """
    Run fraud scoring and AML monitoring for a payment before rail submission.

    Returns APPROVE / HOLD / BLOCK decision with full fraud and AML findings.
    Callers MUST check `decision` before submitting to payment rail.

    After successful rail submission, call the velocity record endpoint
    (or `TxMonitorService.record()`) to update the AML velocity state.
    """
    pipeline = _get_pipeline()

    req = PipelineRequest(
        transaction_id=body.transaction_id,
        customer_id=body.customer_id,
        entity_type=body.entity_type,
        amount=Decimal(body.amount),
        currency=body.currency,
        destination_account=body.destination_account,
        destination_sort_code=body.destination_sort_code,
        destination_country=body.destination_country,
        payment_rail=body.payment_rail,
        device_id=body.device_id,
        customer_ip=body.customer_ip,
        session_id=body.session_id,
        first_transaction_to_payee=body.first_transaction_to_payee,
        amount_unusual=body.amount_unusual,
        is_pep=body.is_pep,
        is_sanctions_hit=body.is_sanctions_hit,
        is_fx=body.is_fx,
    )
    result = pipeline.assess(req)

    return FraudAssessResponse(
        transaction_id=result.transaction_id,
        customer_id=result.customer_id,
        decision=result.decision.value,
        fraud_risk=result.fraud_risk.value,
        fraud_score=result.fraud_score,
        app_scam_indicator=result.app_scam_indicator.value,
        fraud_factors=result.fraud_factors,
        fraud_latency_ms=result.fraud_latency_ms,
        aml_edd_required=result.aml_edd_required,
        aml_velocity_daily_breach=result.aml_velocity_daily_breach,
        aml_velocity_monthly_breach=result.aml_velocity_monthly_breach,
        aml_structuring_signal=result.aml_structuring_signal,
        aml_sar_required=result.aml_sar_required,
        aml_sanctions_block=result.aml_sanctions_block,
        aml_reasons=result.aml_reasons,
        block_reasons=result.block_reasons,
        hold_reasons=result.hold_reasons,
        requires_hitl=result.requires_hitl,
        assessed_at=result.assessed_at,
    )
