"""
services/merchant_acquiring/merchant_risk_scorer.py
IL-MAG-01 | Phase 20

Ongoing merchant risk monitoring: chargeback ratio, volume anomaly, MCC risk.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.merchant_acquiring.models import (
    DisputeStorePort,
    MAAuditPort,
    MerchantRiskScore,
    MerchantRiskTier,
    MerchantStorePort,
    PaymentStorePort,
)

_HIGH_RISK_MCC_SCORES: dict[str, float] = {
    "7995": 80.0,
    "9754": 75.0,
    "6011": 60.0,
    "5912": 40.0,
}


class MerchantRiskScorer:
    """Computes risk scores for merchants based on chargeback, volume, and MCC."""

    def __init__(
        self,
        merchant_store: MerchantStorePort,
        payment_store: PaymentStorePort,
        dispute_store: DisputeStorePort,
        audit: MAAuditPort,
    ) -> None:
        self._merchant_store = merchant_store
        self._payment_store = payment_store
        self._dispute_store = dispute_store
        self._audit = audit

    async def score_merchant(self, merchant_id: str, actor: str = "system") -> MerchantRiskScore:
        """Compute a composite risk score for a merchant."""
        merchant = await self._merchant_store.get(merchant_id)
        if merchant is None:
            raise ValueError(f"Merchant {merchant_id!r} not found")

        payments = await self._payment_store.list_by_merchant(merchant_id)
        disputes = await self._dispute_store.list_by_merchant(merchant_id)

        chargeback_ratio = len(disputes) / max(len(payments), 1)
        volume_anomaly = 0.0  # stub — no historical baseline for InMemory
        mcc_risk = _HIGH_RISK_MCC_SCORES.get(merchant.mcc, 10.0)

        overall = (chargeback_ratio * 40 + volume_anomaly * 30 + mcc_risk * 30) / 100
        risk_tier = self._determine_tier(overall)

        score = MerchantRiskScore(
            merchant_id=merchant_id,
            computed_at=datetime.now(UTC),
            chargeback_ratio=chargeback_ratio,
            volume_anomaly=volume_anomaly,
            mcc_risk=mcc_risk,
            overall_score=overall,
            risk_tier=risk_tier,
        )
        await self._audit.log(
            "risk.scored",
            merchant_id,
            actor,
            {
                "chargeback_ratio": chargeback_ratio,
                "volume_anomaly": volume_anomaly,
                "mcc_risk": mcc_risk,
                "overall_score": overall,
                "risk_tier": risk_tier.value,
            },
        )
        return score

    def _determine_tier(self, score: float) -> MerchantRiskTier:
        """Map overall score to a risk tier."""
        if score < 25:
            return MerchantRiskTier.LOW
        if score < 50:
            return MerchantRiskTier.MEDIUM
        if score < 75:
            return MerchantRiskTier.HIGH
        return MerchantRiskTier.PROHIBITED

    async def flag_high_risk(self, merchant_id: str, reason: str, actor: str) -> None:
        """Flag a merchant as high risk for manual review."""
        await self._audit.log(
            "risk.flagged",
            merchant_id,
            actor,
            {"reason": reason},
        )
