"""
breach_prediction.py — BreachPredictionSkill
Predicts breach probability using moving average + trend.
Pure Python + Decimal math — no ML dependencies.

FCA CASS 15.12 | IL-015 Phase 5 | banxe-emi-stack

Algorithm:
  - Moving average of last N discrepancy amounts (default window=3)
  - Trend: compare first half vs second half of history
  - Probability: normalized moving average vs breach threshold
  - Predicted days: linear extrapolation from trend

All numeric operations use Decimal — never float (I-24).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
import logging

logger = logging.getLogger("banxe.agents.breach_prediction")

# Thresholds (Decimal — never float)
BREACH_THRESHOLD = Decimal("10.00")  # £10 minimum reportable discrepancy (BREACH_AMOUNT_GBP)
MAX_BREACH_DISCREPANCY = Decimal("100000.00")  # normalization cap


@dataclass(frozen=True)
class PredictionResult:
    """Breach prediction for one safeguarding account.

    All probabilities are Decimal (0.00 to 1.00 — never float, I-24).
    Frozen dataclass — immutable for audit integrity.
    """

    account_id: str
    probability: Decimal  # 0.00 to 1.00 — Decimal, never float
    predicted_breach_in_days: int | None  # None if no breach predicted
    trend: str  # "IMPROVING" | "STABLE" | "DETERIORATING"
    confidence: Decimal  # 0.00 to 1.00 — confidence in prediction


class BreachPredictionSkill:
    """
    Predicts breach based on discrepancy history using moving average.

    Usage:
        skill = BreachPredictionSkill()
        history = [
            {"date": date(2026, 4, 8), "discrepancy": Decimal("500.00"), "status": "DISCREPANCY"},
            {"date": date(2026, 4, 9), "discrepancy": Decimal("800.00"), "status": "DISCREPANCY"},
            {"date": date(2026, 4, 10), "discrepancy": Decimal("1200.00"), "status": "DISCREPANCY"},
        ]
        result = skill.predict("account-001", history)
        # result.trend == "DETERIORATING", result.probability > 0.5
    """

    def predict(self, account_id: str, history: list[dict]) -> PredictionResult:
        """
        Predict breach probability for an account.

        Args:
            account_id: Midaz account UUID
            history: list of {"date": date, "discrepancy": Decimal, "status": str}
                     sorted by date (oldest first)

        Returns:
            PredictionResult with probability, trend, and predicted days to breach.
        """
        if not history:
            return PredictionResult(
                account_id=account_id,
                probability=Decimal("0.00"),
                predicted_breach_in_days=None,
                trend="STABLE",
                confidence=Decimal("0.50"),
            )

        # Extract discrepancy values as Decimal (filter MATCHED = 0)
        values: list[Decimal] = []
        for h in history:
            status = h.get("status", "")
            if status == "MATCHED":
                values.append(Decimal("0.00"))
            else:
                disc = h.get("discrepancy", Decimal("0"))
                values.append(abs(Decimal(str(disc))))

        # All MATCHED → no breach predicted
        if all(v == Decimal("0") for v in values):
            return PredictionResult(
                account_id=account_id,
                probability=Decimal("0.00"),
                predicted_breach_in_days=None,
                trend="STABLE",
                confidence=Decimal("0.90"),
            )

        # Moving average
        ma = self._moving_average(values)

        # Trend analysis
        trend = self._trend(values)

        # Probability: normalized MA vs cap, then clamped to [0, 1]
        raw_prob = ma / MAX_BREACH_DISCREPANCY
        probability = min(Decimal("1.00"), max(Decimal("0.00"), raw_prob))
        # Round to 2 decimal places
        probability = probability.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Days to breach prediction
        predicted_days = self._predict_days_to_breach(values, trend)

        # Confidence: higher with more data points
        n = len(values)
        if n >= 7:
            confidence = Decimal("0.85")
        elif n >= 3:
            confidence = Decimal("0.70")
        else:
            confidence = Decimal("0.50")

        return PredictionResult(
            account_id=account_id,
            probability=probability,
            predicted_breach_in_days=predicted_days,
            trend=trend,
            confidence=confidence,
        )

    def _moving_average(self, values: list[Decimal], window: int = 3) -> Decimal:
        """
        Calculate moving average of last N values.

        Args:
            values: list of Decimal discrepancy amounts
            window: number of recent values to average (default 3)

        Returns:
            Decimal moving average (0 if no values)
        """
        if not values:
            return Decimal("0.00")
        recent = values[-window:]
        total = sum(recent, Decimal("0"))
        return total / Decimal(len(recent))

    def _trend(self, values: list[Decimal]) -> str:
        """
        Determine trend: IMPROVING if decreasing, DETERIORATING if increasing, STABLE otherwise.

        Compares average of first half vs second half of history.
        Requires at least 2 values for meaningful comparison.
        """
        if len(values) < 2:
            return "STABLE"

        mid = len(values) // 2
        first_half = values[:mid] if mid > 0 else [values[0]]
        second_half = values[mid:] if mid > 0 else [values[-1]]

        avg_first = sum(first_half, Decimal("0")) / Decimal(len(first_half))
        avg_second = sum(second_half, Decimal("0")) / Decimal(len(second_half))

        # 5% tolerance band for STABLE
        tolerance = avg_first * Decimal("0.05") if avg_first > 0 else Decimal("1.00")

        diff = avg_second - avg_first
        if diff > tolerance:
            return "DETERIORATING"
        elif diff < -tolerance:
            return "IMPROVING"
        else:
            return "STABLE"

    def _predict_days_to_breach(self, values: list[Decimal], trend: str) -> int | None:
        """
        Predict days to FCA breach threshold (3 consecutive days per BREACH_DAYS).

        Returns None if trend is IMPROVING or STABLE with low discrepancy.
        Returns integer days estimate if DETERIORATING trend detected.
        """
        if trend == "IMPROVING":
            return None

        ma = self._moving_average(values)
        if ma <= BREACH_THRESHOLD:
            return None

        # Consecutive discrepancy days already in history
        consecutive = 0
        for v in reversed(values):
            if v > BREACH_THRESHOLD:
                consecutive += 1
            else:
                break

        # FCA breach = 3 consecutive days
        days_remaining = max(0, 3 - consecutive)
        if days_remaining == 0:
            return 0  # already at breach
        return days_remaining
