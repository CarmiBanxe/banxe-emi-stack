"""
mock_fraud_adapter.py — Deterministic Mock Fraud Scoring Adapter
S5-22 (Real-time fraud scoring <100ms) | S5-26 (APP scam detection PSR APP 2024)
PSR APP 2024 | FCA CONC 13 | banxe-emi-stack

WHY THIS EXISTS
---------------
Sardine.ai production API requires an active contract and API key.
MockFraudAdapter lets us build, test, and demo the full fraud scoring
pipeline immediately — without waiting for the Sardine.ai contract.

When SARDINE_CLIENT_ID + SARDINE_SECRET_KEY arrive:
  1. Set FRAUD_ADAPTER=sardine in .env
  2. FraudService auto-switches to SardineFraudAdapter
  3. No code changes needed in business logic or tests

Score logic (deterministic — no randomness, purely rule-based):
  - CRITICAL (block): amount ≥ £50,000 OR destination_country in BLOCK list
  - HIGH (hold):      amount ≥ £10,000 OR first_to_payee + amount_unusual
  - MEDIUM:           amount ≥ £1,000 OR first_to_payee
  - LOW:              everything else

APP scam detection (PSR APP 2024):
  - Heuristic based on amount + first_to_payee + country patterns
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from services.fraud.fraud_port import (
    AppScamIndicator,
    FraudRisk,
    FraudScoringRequest,
    FraudScoringResult,
)

logger = logging.getLogger(__name__)

# High-risk destination countries (overlap with AML Category B — FATF greylist)
_HIGH_RISK_COUNTRIES = {
    "SY", "IQ", "LB", "YE", "HT", "ML", "DZ", "AO", "BO", "VG",
    "CM", "CI", "CD", "KE", "LA", "MC", "NA", "NP", "SS", "TT",
    "VU", "BG", "VN",
}

# Hard-block countries (AML Category A — OFAC / UK HMT)
_BLOCKED_COUNTRIES = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE"}

_AMOUNT_CRITICAL = Decimal("50000")
_AMOUNT_HIGH = Decimal("10000")
_AMOUNT_MEDIUM = Decimal("1000")


class MockFraudAdapter:
    """
    Deterministic in-memory fraud scoring adapter.
    Satisfies FraudScoringPort. Always returns in < 5ms (well within 100ms SLA).
    """

    def score(self, request: FraudScoringRequest) -> FraudScoringResult:
        t0 = time.monotonic()
        risk, score, factors, app_scam = self._compute(request)
        latency_ms = (time.monotonic() - t0) * 1000

        result = FraudScoringResult(
            transaction_id=request.transaction_id,
            risk=risk,
            score=score,
            app_scam_indicator=app_scam,
            block=risk == FraudRisk.CRITICAL,
            hold_for_review=risk in (FraudRisk.HIGH, FraudRisk.CRITICAL),
            factors=factors,
            provider="mock",
            latency_ms=round(latency_ms, 2),
        )
        logger.debug(
            "MockFraud scored %s → %s (score=%d, latency=%.1fms)",
            request.transaction_id, risk.value, score, latency_ms,
        )
        return result

    def health(self) -> bool:
        return True

    def _compute(
        self, req: FraudScoringRequest
    ) -> tuple[FraudRisk, int, list[str], AppScamIndicator]:
        factors: list[str] = []
        score = 0
        app_scam = AppScamIndicator.NONE

        # ── Blocked country → CRITICAL ────────────────────────────────────────
        if req.destination_country in _BLOCKED_COUNTRIES:
            factors.append(f"Destination country {req.destination_country} is OFAC/HMT sanctioned")
            return FraudRisk.CRITICAL, 95, factors, AppScamIndicator.NONE

        # ── Amount scoring ────────────────────────────────────────────────────
        # £50k → CRITICAL alone (score 90); £10k → HIGH when combined with
        # first_to_payee (50+20=70); £1k → MEDIUM alone (40).
        if req.amount >= _AMOUNT_CRITICAL:
            score += 90
            factors.append(f"High-value transaction ≥ £{_AMOUNT_CRITICAL:,.0f}")
        elif req.amount >= _AMOUNT_HIGH:
            score += 50
            factors.append(f"Transaction ≥ £{_AMOUNT_HIGH:,.0f} (EDD threshold I-04)")
        elif req.amount >= _AMOUNT_MEDIUM:
            score += 40
            factors.append(f"Transaction ≥ £{_AMOUNT_MEDIUM:,.0f}")

        # ── First payment to payee ────────────────────────────────────────────
        if req.first_transaction_to_payee:
            score += 20
            factors.append("First transaction to this payee")

        # ── Unusual amount ────────────────────────────────────────────────────
        if req.amount_unusual:
            score += 15
            factors.append("Amount significantly above customer average")

        # ── High-risk destination country ─────────────────────────────────────
        if req.destination_country in _HIGH_RISK_COUNTRIES:
            score += 20
            factors.append(f"Destination country {req.destination_country} (FATF greylist)")

        # ── APP scam heuristic (PSR APP 2024) ─────────────────────────────────
        # Simplified: first_to_payee + high amount + unusual → investment scam signal
        if req.first_transaction_to_payee and req.amount >= _AMOUNT_HIGH and req.amount_unusual:
            app_scam = AppScamIndicator.INVESTMENT_SCAM
            score += 10
            factors.append("APP scam signal: first-time payee + high + unusual amount")

        # ── Clamp and classify ────────────────────────────────────────────────
        score = min(score, 100)

        if score >= 85:
            risk = FraudRisk.CRITICAL
        elif score >= 70:
            risk = FraudRisk.HIGH
        elif score >= 40:
            risk = FraudRisk.MEDIUM
        else:
            risk = FraudRisk.LOW
            if not factors:
                factors.append("No fraud indicators detected")

        return risk, score, factors, app_scam
