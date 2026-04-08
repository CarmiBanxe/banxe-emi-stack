"""
services/hitl/hitl_service.py — HITL Review Queue Service
IL-051 | Phase 2 #10 | banxe-emi-stack

In-memory implementation of HITLPort.
In production: swap for ClickHouse / Postgres persistence.

Key invariants enforced here:
  I-27: feedback corpus is WRITE-ONLY from this service.
        feedback_loop.py reads it and PROPOSES patches.
        No autonomous model updates.
  I-04: EDD + HITL mandatory — cases cannot be silently dropped.
  EU AI Act Art.14: every AI HOLD decision is traceable to a human decision.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from services.hitl.hitl_port import (
    CaseStatus,
    DecisionOutcome,
    HITLDecision,
    HITLStats,
    ReviewCase,
    ReviewReason,
)

logger = logging.getLogger(__name__)


class HITLCaseError(Exception):
    """Raised for invalid HITL operations."""


class HITLService:
    """
    In-memory HITL Review Queue.

    Thread-safety note: in production, replace in-memory dict with
    a ClickHouse/Postgres-backed store with row-level locking.
    For sandbox/dev: single-threaded usage is assumed.
    """

    def __init__(self) -> None:
        self._cases: dict[str, ReviewCase] = {}
        self._corpus: list[dict] = []          # feedback corpus (I-27)

    # ── Enqueue ───────────────────────────────────────────────────────────────

    def enqueue(
        self,
        transaction_id: str,
        customer_id: str,
        entity_type: str,
        amount: Decimal,
        currency: str,
        reasons: list[ReviewReason],
        fraud_score: int,
        fraud_risk: str,
        aml_flags: list[str],
        hold_reasons: list[str],
    ) -> ReviewCase:
        """
        Add a HOLD case to the review queue.
        SLA is set automatically: 4h for SAR, 24h for all other reasons.
        """
        case_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        sla_h = ReviewCase.sla_hours(reasons)
        expires_at = now + timedelta(hours=sla_h)

        case = ReviewCase(
            case_id=case_id,
            transaction_id=transaction_id,
            customer_id=customer_id,
            entity_type=entity_type,
            amount=amount,
            currency=currency,
            reasons=list(reasons),
            fraud_score=fraud_score,
            fraud_risk=fraud_risk,
            aml_flags=list(aml_flags),
            hold_reasons=list(hold_reasons),
            status=CaseStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
        )
        self._cases[case_id] = case
        logger.info(
            "HITL enqueued: case=%s tx=%s customer=%s amount=£%s "
            "reasons=%s sla=%dh",
            case_id, transaction_id, customer_id, amount,
            [r.value for r in reasons], sla_h,
        )
        return case

    @classmethod
    def from_pipeline_result(
        cls_or_self,
        pipeline_result,   # type: ignore[no-untyped-def]
        service: "HITLService",
    ) -> ReviewCase:
        """
        Convenience builder: create a ReviewCase from a FraudAMLPipeline result.
        Call this when pipeline.assess() returns decision=HOLD.

        Usage:
            result = pipeline.assess(req)
            if result.decision == PipelineDecision.HOLD:
                case = HITLService.from_pipeline_result(result, hitl_service)
        """
        # Map pipeline AML flags → ReviewReasons
        reasons: list[ReviewReason] = []
        if pipeline_result.fraud_risk in ("HIGH",):
            reasons.append(ReviewReason.FRAUD_HIGH)
        if pipeline_result.app_scam_indicator.value != "NONE":
            reasons.append(ReviewReason.APP_SCAM)
        if pipeline_result.aml_edd_required:
            reasons.append(ReviewReason.EDD_REQUIRED)
        if pipeline_result.aml_velocity_daily_breach:
            reasons.append(ReviewReason.VELOCITY_DAILY)
        if pipeline_result.aml_velocity_monthly_breach:
            reasons.append(ReviewReason.VELOCITY_MONTHLY)
        if pipeline_result.aml_structuring_signal:
            reasons.append(ReviewReason.STRUCTURING)
        if pipeline_result.aml_sar_required:
            reasons.append(ReviewReason.SAR_REQUIRED)
        if not reasons:
            reasons.append(ReviewReason.AML_COMBINED)

        return service.enqueue(
            transaction_id=pipeline_result.transaction_id,
            customer_id=pipeline_result.customer_id,
            entity_type="INDIVIDUAL",         # pipeline doesn't carry entity_type
            amount=Decimal("0"),              # pipeline doesn't carry amount directly
            currency="GBP",
            reasons=reasons,
            fraud_score=pipeline_result.fraud_score,
            fraud_risk=pipeline_result.fraud_risk.value,
            aml_flags=pipeline_result.aml_reasons,
            hold_reasons=pipeline_result.hold_reasons,
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_case(self, case_id: str) -> Optional[ReviewCase]:
        return self._cases.get(case_id)

    def list_queue(
        self, status: Optional[CaseStatus] = None
    ) -> list[ReviewCase]:
        """
        List cases, optionally filtered by status.
        Expired PENDING cases are auto-marked as EXPIRED on read.
        """
        self._expire_stale_cases()
        cases = list(self._cases.values())
        if status is not None:
            cases = [c for c in cases if c.status == status]
        # Sort: SAR cases first (urgent), then by created_at ascending
        return sorted(
            cases,
            key=lambda c: (
                ReviewReason.SAR_REQUIRED not in c.reasons,
                c.created_at,
            ),
        )

    # ── Decide ────────────────────────────────────────────────────────────────

    def decide(
        self,
        case_id: str,
        outcome: DecisionOutcome,
        decided_by: str,
        notes: str = "",
    ) -> ReviewCase:
        """
        Record a human decision on a HOLD case.
        Writes to feedback corpus (I-27: supervised loop, not autonomous).

        Raises HITLCaseError if case not found or already decided.
        """
        case = self._cases.get(case_id)
        if case is None:
            raise HITLCaseError(f"Case {case_id} not found")
        if case.status != CaseStatus.PENDING:
            raise HITLCaseError(
                f"Case {case_id} is already {case.status.value} — cannot re-decide"
            )

        now = datetime.now(timezone.utc)

        # Update case (dataclass is not frozen — mutate in place)
        case.status = {
            DecisionOutcome.APPROVE:   CaseStatus.APPROVED,
            DecisionOutcome.REJECT:    CaseStatus.REJECTED,
            DecisionOutcome.ESCALATE:  CaseStatus.ESCALATED,
        }[outcome]
        case.decision = outcome
        case.decided_at = now
        case.decision_by = decided_by
        case.decision_notes = notes

        # Write to feedback corpus (I-27: supervised feedback loop)
        feedback = HITLDecision(
            case_id=case_id,
            transaction_id=case.transaction_id,
            customer_id=case.customer_id,
            amount=case.amount,
            fraud_score=case.fraud_score,
            reasons=[r.value for r in case.reasons],
            outcome=outcome,
            decided_by=decided_by,
            decided_at=now,
            notes=notes,
        )
        self._corpus.append(feedback.to_corpus_record())

        logger.info(
            "HITL decision: case=%s tx=%s outcome=%s by=%s",
            case_id, case.transaction_id, outcome.value, decided_by,
        )
        return case

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> HITLStats:
        """Compute queue metrics for FCA Consumer Duty reporting."""
        self._expire_stale_cases()
        cases = list(self._cases.values())

        by_status = {s: 0 for s in CaseStatus}
        for c in cases:
            by_status[c.status] += 1

        decided = [
            c for c in cases
            if c.decided_at and c.status in (
                CaseStatus.APPROVED, CaseStatus.REJECTED, CaseStatus.ESCALATED
            )
        ]
        avg_resolution = 0.0
        if decided:
            total_h = sum(
                (c.decided_at - c.created_at).total_seconds() / 3600
                for c in decided
            )
            avg_resolution = round(total_h / len(decided), 2)

        approved = by_status[CaseStatus.APPROVED]
        rejected = by_status[CaseStatus.REJECTED]
        approval_rate = 0.0
        if (approved + rejected) > 0:
            approval_rate = round(approved / (approved + rejected) * 100, 1)

        pending = [c for c in cases if c.status == CaseStatus.PENDING]
        oldest_h = 0.0
        if pending:
            oldest = min(c.created_at for c in pending)
            oldest_h = round(
                (datetime.now(timezone.utc) - oldest).total_seconds() / 3600, 2
            )

        return HITLStats(
            total_cases=len(cases),
            pending_cases=by_status[CaseStatus.PENDING],
            approved_cases=approved,
            rejected_cases=rejected,
            escalated_cases=by_status[CaseStatus.ESCALATED],
            expired_cases=by_status[CaseStatus.EXPIRED],
            approval_rate=approval_rate,
            avg_resolution_hours=avg_resolution,
            oldest_pending_hours=oldest_h,
        )

    # ── Feedback corpus (I-27) ─────────────────────────────────────────────────

    def get_feedback_corpus(self) -> list[dict]:
        """
        Return all recorded human decisions as JSON-compatible dicts.

        feedback_loop.py reads this corpus to analyse decision patterns
        and PROPOSE threshold adjustments — it never applies them.
        (I-27: supervised feedback loop, not autonomous self-improvement)
        """
        return list(self._corpus)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _expire_stale_cases(self) -> None:
        """Mark PENDING cases past their SLA as EXPIRED."""
        now = datetime.now(timezone.utc)
        for case in self._cases.values():
            if case.status == CaseStatus.PENDING and now > case.expires_at:
                case.status = CaseStatus.EXPIRED
                logger.warning(
                    "HITL SLA EXPIRED: case=%s tx=%s sla_breach=%.1fh",
                    case.case_id, case.transaction_id,
                    (now - case.expires_at).total_seconds() / 3600,
                )
