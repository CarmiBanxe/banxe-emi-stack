"""
services/fraud/fraud_aml_pipeline.py — Fraud + AML Orchestration Pipeline
IL-049 | S9-05 | banxe-emi-stack

Combines real-time fraud scoring (FraudScoringPort) and AML transaction
monitoring (TxMonitorService) into a single pre-payment gate.

PIPELINE FLOW (must complete before payment rail submission):
  1. Fraud scoring via FraudScoringPort (Sardine / Mock)
  2. AML monitoring via TxMonitorService (velocity, EDD, structuring, SAR)
  3. Decision matrix → APPROVE / HOLD / BLOCK

DECISION MATRIX (priority: BLOCK > HOLD > APPROVE):
  BLOCK:
    - fraud_result.block = True (fraud score ≥ 85 OR blocked country)
    - aml_result.sanctions_block = True (I-06 HARD_BLOCK)

  HOLD (HITL required):
    - fraud_result.risk = HIGH (score 70-84, hold_for_review without block)
    - fraud_result.app_scam_indicator ≠ NONE (PSR APP 2024)
    - aml_result.sar_required (POCA 2002 — MLRO review)
    - aml_result.edd_required (MLR 2017 Reg.28 — EDD gate before proceeding)
    - aml_result.velocity_daily_breach
    - aml_result.velocity_monthly_breach
    - aml_result.structuring_signal (POCA 2002 s.330)

  APPROVE: all other cases

FCA compliance:
  - PSR APP 2024: mandatory APP scam detection gate
  - MLR 2017 Reg.28: EDD gate before processing transactions ≥ threshold
  - POCA 2002 s.330: structuring detection
  - I-06: sanctions hard block (non-negotiable)
  - I-04: EDD trigger (£10k individual / £50k company)
  - All decisions logged for FCA audit trail (caller's responsibility)

NOTE: record() (velocity update) must be called by the payment service
AFTER rail submission succeeds, NOT here. This pipeline only assesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import logging
import time

from services.aml.tx_monitor import TxMonitorRequest, TxMonitorService
from services.fraud.fraud_port import (
    AppScamIndicator,
    FraudRisk,
    FraudScoringPort,
    FraudScoringRequest,
)

logger = logging.getLogger(__name__)


# ── Pipeline request / result ──────────────────────────────────────────────────


@dataclass(frozen=True)
class PipelineRequest:
    """
    Single transaction submitted to the Fraud + AML pipeline.
    Built by payment service before rail submission.
    """

    transaction_id: str
    customer_id: str
    entity_type: str  # "INDIVIDUAL" | "COMPANY"
    amount: Decimal  # GBP-equivalent amount
    currency: str
    destination_account: str  # IBAN or account number
    destination_sort_code: str  # UK sort code (empty for SEPA)
    destination_country: str  # ISO-3166-1 alpha-2
    payment_rail: str  # FPS / SEPA_CT / SEPA_INSTANT / BACS
    device_id: str | None = None
    customer_ip: str | None = None
    session_id: str | None = None
    first_transaction_to_payee: bool = True
    amount_unusual: bool = False
    is_pep: bool = False
    is_sanctions_hit: bool = False  # Pre-screened via sanctions service
    is_fx: bool = False


class PipelineDecision(str, Enum):
    """
    Final gate decision.
    BLOCK = payment must not proceed (fraud CRITICAL or sanctions).
    HOLD  = payment must not proceed until HITL review clears it.
    APPROVE = payment may proceed to rail submission.
    """

    APPROVE = "APPROVE"
    HOLD = "HOLD"
    BLOCK = "BLOCK"


@dataclass
class PipelineResult:
    """
    Combined Fraud + AML assessment result for one transaction.

    Callers must check `decision` before submitting to payment rail:
      if result.decision == PipelineDecision.BLOCK → reject immediately
      if result.decision == PipelineDecision.HOLD  → queue for HITL
      if result.decision == PipelineDecision.APPROVE → proceed
    """

    transaction_id: str
    customer_id: str
    decision: PipelineDecision

    # ── Fraud findings ──────────────────────────────────────────────────────
    fraud_risk: FraudRisk
    fraud_score: int
    app_scam_indicator: AppScamIndicator
    fraud_factors: list[str]
    fraud_latency_ms: float

    # ── AML findings ────────────────────────────────────────────────────────
    aml_edd_required: bool
    aml_velocity_daily_breach: bool
    aml_velocity_monthly_breach: bool
    aml_structuring_signal: bool
    aml_sar_required: bool
    aml_sanctions_block: bool
    aml_reasons: list[str]

    # ── Decision reasons ────────────────────────────────────────────────────
    block_reasons: list[str]
    hold_reasons: list[str]

    # ── Meta ────────────────────────────────────────────────────────────────
    requires_hitl: bool
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def approved(self) -> bool:
        return self.decision == PipelineDecision.APPROVE


# ── Orchestrator ───────────────────────────────────────────────────────────────


class FraudAMLPipeline:
    """
    Pre-payment fraud and AML gate.

    Usage (payment service):
        pipeline = FraudAMLPipeline(fraud_adapter, tx_monitor)
        result = pipeline.assess(PipelineRequest(...))
        if result.decision == PipelineDecision.BLOCK:
            raise PaymentRejected("Fraud/sanctions block")
        if result.decision == PipelineDecision.HOLD:
            queue_for_hitl(result)
            return
        # → proceed to rail submission
        rail.submit(payment)
        # After success: record velocity
        tx_monitor.record(customer_id, amount)
    """

    def __init__(
        self,
        fraud_adapter: FraudScoringPort,
        tx_monitor: TxMonitorService,
    ) -> None:
        self._fraud = fraud_adapter
        self._monitor = tx_monitor

    def assess(self, req: PipelineRequest) -> PipelineResult:
        """
        Run fraud scoring + AML monitoring sequentially.
        Returns PipelineResult with final APPROVE / HOLD / BLOCK decision.

        Designed to be called synchronously (fraud SLA: <100ms — S5-22).
        AML monitoring uses cached velocity data (no network calls).
        """
        t0 = time.monotonic()

        # ── 1. Fraud scoring ─────────────────────────────────────────────────
        fraud_req = FraudScoringRequest(
            transaction_id=req.transaction_id,
            customer_id=req.customer_id,
            amount=req.amount,
            currency=req.currency,
            destination_account=req.destination_account,
            destination_sort_code=req.destination_sort_code,
            destination_country=req.destination_country,
            payment_rail=req.payment_rail,
            customer_device_id=req.device_id,
            customer_ip=req.customer_ip,
            session_id=req.session_id,
            first_transaction_to_payee=req.first_transaction_to_payee,
            amount_unusual=req.amount_unusual,
            entity_type=req.entity_type,
        )
        fraud_result = self._fraud.score(fraud_req)
        fraud_latency_ms = fraud_result.latency_ms

        # ── 2. AML monitoring ─────────────────────────────────────────────────
        aml_req = TxMonitorRequest(
            transaction_id=req.transaction_id,
            customer_id=req.customer_id,
            entity_type=req.entity_type,
            amount=req.amount,
            currency=req.currency,
            is_pep=req.is_pep,
            is_sanctions_hit=req.is_sanctions_hit,
            is_fx=req.is_fx,
        )
        aml_result = self._monitor.evaluate(aml_req)

        # ── 3. Decision matrix ────────────────────────────────────────────────
        block_reasons: list[str] = []
        hold_reasons: list[str] = []

        # BLOCK conditions (non-negotiable)
        if fraud_result.block:
            block_reasons.append(
                f"Fraud CRITICAL (score={fraud_result.score}): " + "; ".join(fraud_result.factors)
            )
        if aml_result.sanctions_block:
            block_reasons.append("Sanctions hard block (I-06): " + "; ".join(aml_result.reasons))

        # HOLD conditions (HITL required before proceeding)
        if fraud_result.hold_for_review and not fraud_result.block:
            # HIGH risk (70-84) — hold but not outright block
            hold_reasons.append(
                f"Fraud HIGH (score={fraud_result.score}): " + "; ".join(fraud_result.factors)
            )
        if fraud_result.app_scam_indicator != AppScamIndicator.NONE:
            hold_reasons.append(
                f"APP scam signal (PSR APP 2024): {fraud_result.app_scam_indicator.value}"
            )
        if aml_result.sar_required:
            hold_reasons.extend(r for r in aml_result.reasons if "SAR" in r)
            if not any("SAR" in r for r in aml_result.reasons):
                hold_reasons.append("SAR consideration required (MLRO review)")
        if aml_result.edd_required:
            hold_reasons.extend(r for r in aml_result.reasons if "EDD" in r or "edd" in r.lower())
        if aml_result.velocity_daily_breach:
            hold_reasons.extend(r for r in aml_result.reasons if "Daily velocity" in r)
        if aml_result.velocity_monthly_breach:
            hold_reasons.extend(r for r in aml_result.reasons if "Monthly velocity" in r)
        if aml_result.structuring_signal:
            hold_reasons.extend(r for r in aml_result.reasons if "structuring" in r.lower())

        # Final decision (BLOCK > HOLD > APPROVE)
        if block_reasons:
            decision = PipelineDecision.BLOCK
        elif hold_reasons:
            decision = PipelineDecision.HOLD
        else:
            decision = PipelineDecision.APPROVE

        total_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "FraudAML assess: tx=%s customer=%s entity=%s amount=£%s "
            "decision=%s fraud=%s(score=%d) aml_flags=%s latency=%.1fms",
            req.transaction_id,
            req.customer_id,
            req.entity_type,
            req.amount,
            decision.value,
            fraud_result.risk.value,
            fraud_result.score,
            _active_aml_flags(aml_result),
            total_ms,
        )

        return PipelineResult(
            transaction_id=req.transaction_id,
            customer_id=req.customer_id,
            decision=decision,
            fraud_risk=fraud_result.risk,
            fraud_score=fraud_result.score,
            app_scam_indicator=fraud_result.app_scam_indicator,
            fraud_factors=fraud_result.factors,
            fraud_latency_ms=fraud_latency_ms,
            aml_edd_required=aml_result.edd_required,
            aml_velocity_daily_breach=aml_result.velocity_daily_breach,
            aml_velocity_monthly_breach=aml_result.velocity_monthly_breach,
            aml_structuring_signal=aml_result.structuring_signal,
            aml_sar_required=aml_result.sar_required,
            aml_sanctions_block=aml_result.sanctions_block,
            aml_reasons=aml_result.reasons,
            block_reasons=block_reasons,
            hold_reasons=hold_reasons,
            requires_hitl=decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK),
        )


def _active_aml_flags(aml_result) -> list[str]:  # type: ignore[no-untyped-def]
    """Return list of active AML flag names for logging."""
    flags = []
    if aml_result.sanctions_block:
        flags.append("SANCTIONS")
    if aml_result.edd_required:
        flags.append("EDD")
    if aml_result.velocity_daily_breach:
        flags.append("VEL_D")
    if aml_result.velocity_monthly_breach:
        flags.append("VEL_M")
    if aml_result.structuring_signal:
        flags.append("STRUCT")
    if aml_result.sar_required:
        flags.append("SAR")
    return flags
