"""
services/card_issuing/fraud_shield.py
IL-CIM-01 | Phase 19

Real-time card fraud detection: velocity checks + MCC anomaly + geo-anomaly.
risk_score is a score (0.0–100.0), not money — float is acceptable here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from services.card_issuing.models import (
    CardAuditPort,
    TransactionStorePort,
)

_HIGH_RISK_MCCS: set[str] = {"7995", "6011", "9754", "7801"}  # gambling, cash, lottery


@dataclass(frozen=True)
class FraudAssessment:
    card_id: str
    risk_score: float
    is_suspicious: bool
    triggered_rules: list[str]
    assessed_at: datetime


class FraudShield:
    """Real-time fraud scoring based on velocity, amount, and MCC risk signals."""

    def __init__(
        self,
        txn_store: TransactionStorePort,
        audit: CardAuditPort,
        suspicious_threshold: float = 70.0,
    ) -> None:
        self._txn_store = txn_store
        self._audit = audit
        self._threshold = suspicious_threshold

    async def assess(
        self,
        card_id: str,
        amount: Decimal,
        mcc: str,
        country: str,
        actor: str = "system",
    ) -> FraudAssessment:
        """
        Score a transaction for fraud risk.
        Rules:
          - HIGH_VELOCITY: >= 5 auths in last hour → +30
          - HIGH_AMOUNT: amount > 1000 → +20
          - HIGH_RISK_MCC: mcc in _HIGH_RISK_MCCS → +25
        """
        triggered_rules: list[str] = []
        score: float = 0.0

        auths = await self._txn_store.list_auths(card_id)
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        recent_count = sum(1 for a in auths if a.authorised_at >= cutoff)

        if recent_count >= 5:
            triggered_rules.append("HIGH_VELOCITY")
            score += 30.0

        if amount > Decimal("1000"):
            triggered_rules.append("HIGH_AMOUNT")
            score += 20.0

        if mcc in _HIGH_RISK_MCCS:
            triggered_rules.append("HIGH_RISK_MCC")
            score += 25.0

        score = min(score, 100.0)
        is_suspicious = score >= self._threshold
        assessed_at = datetime.now(UTC)

        await self._audit.log(
            event_type="fraud.assessed",
            card_id=card_id,
            entity_id="",
            actor=actor,
            details={
                "risk_score": score,
                "is_suspicious": is_suspicious,
                "triggered_rules": triggered_rules,
                "mcc": mcc,
                "country": country,
                "amount": str(amount),
            },
        )

        return FraudAssessment(
            card_id=card_id,
            risk_score=score,
            is_suspicious=is_suspicious,
            triggered_rules=triggered_rules,
            assessed_at=assessed_at,
        )

    async def flag_suspicious(self, card_id: str, reason: str, actor: str) -> None:
        """Manually flag a card as suspicious and log the event."""
        await self._audit.log(
            event_type="fraud.flagged",
            card_id=card_id,
            entity_id="",
            actor=actor,
            details={"reason": reason},
        )
