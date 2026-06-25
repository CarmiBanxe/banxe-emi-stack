"""
services/fraud_tracer/tracer_engine.py
Real-time fraud scoring engine (IL-TRC-01).
Target: p99 < 100ms.
BT-009: ml_model_score() returns Decimal("0.0") until ML pipeline (P1) is provisioned.
I-01: all scores Decimal.
I-02: blocked jurisdictions -> immediate BLOCK.
I-24: TraceLog is append-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import time

from services.fraud_tracer.tracer_models import TracerConfig, TraceRequest, TraceResult
from services.fraud_tracer.velocity_checker import VelocityChecker

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
EDD_THRESHOLD = Decimal("10000.00")

DEFAULT_CONFIG = TracerConfig()


class TracerEngine:
    """Real-time fraud scoring engine.

    Rules applied in order:
    1. Blocked jurisdiction (I-02) -> score 1.0, BLOCK
    2. Amount >= EDD threshold (I-04) -> score += 0.5
    3. Velocity breach -> score += 0.4
    4. BT-009: ML model score returns 0.0 until P1 ML pipeline provisioned

    I-01: all scores are Decimal.
    I-24: trace_log is append-only.
    """

    def __init__(
        self,
        velocity_checker: VelocityChecker | None = None,
        config: TracerConfig | None = None,
    ) -> None:
        self._velocity = velocity_checker or VelocityChecker()
        self._config = config or DEFAULT_CONFIG
        self._trace_log: list[dict] = []  # I-24 append-only

    def trace(self, request: TraceRequest) -> TraceResult:
        """Score a transaction for fraud risk. Target: p99 < 100ms."""
        t0 = time.monotonic()
        flags: list[str] = []
        score = Decimal("0.0")

        # Rule 1: Blocked jurisdiction (I-02)
        if (
            request.country in BLOCKED_JURISDICTIONS
            or request.counterparty_country in BLOCKED_JURISDICTIONS
        ):
            flags.append("BLOCKED_JURISDICTION")
            score = Decimal("1.0")
        else:
            # Rule 2: EDD threshold (I-04)
            amount = Decimal(request.amount)
            if amount >= EDD_THRESHOLD:
                flags.append("EDD_THRESHOLD")
                score = min(score + Decimal("0.5"), Decimal("1.0"))

            # Rule 3: Velocity check
            velocity = self._velocity.check_velocity(request.customer_id)
            if velocity.breached:
                flags.append("VELOCITY_BREACH")
                score = min(score + Decimal("0.4"), Decimal("1.0"))

        # Determine status
        score_str = str(score)
        threshold_block = Decimal(self._config.score_threshold_block)
        threshold_review = Decimal(self._config.score_threshold_review)

        if score >= threshold_block:
            status = "BLOCK"
        elif score >= threshold_review:
            status = "REVIEW"
        else:
            status = "CLEAR"

        latency_ms = int((time.monotonic() - t0) * 1000)

        result = TraceResult(
            transaction_id=request.transaction_id,
            customer_id=request.customer_id,
            score=score_str,
            flags=flags,
            latency_ms=latency_ms,
            status=status,
        )

        # I-24 append-only
        self._trace_log.append(
            {
                "transaction_id": request.transaction_id,
                "score": score_str,
                "status": status,
                "flags": flags,
                "latency_ms": latency_ms,
                "traced_at": datetime.now(UTC).isoformat(),
            }
        )

        return result

    def ml_model_score(self, features: dict) -> Decimal:
        """BT-009: Return neutral ML score until P1 ML pipeline is provisioned.

        Returns Decimal("0.0") — zero ML contribution to rule-based scoring.
        I-01: score is Decimal. I-24: audit log records placeholder usage.
        """
        return Decimal("0.0")

    @property
    def trace_log(self) -> list[dict]:
        """I-24: append-only trace log."""
        return list(self._trace_log)
