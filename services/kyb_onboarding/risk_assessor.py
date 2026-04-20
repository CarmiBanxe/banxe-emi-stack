from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.kyb_onboarding.models import (
    ApplicationStore,
    BusinessType,
    KYBRiskAssessment,
    RiskTier,
    UBOStore,
)

_BLOCKED = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
_HIGH_RISK = {"AF", "MM", "VE", "SY"}  # already in BLOCKED, but explicit
_MEDIUM_RISK = {"PK", "AE", "JO", "TN", "VN", "LK", "NG", "ET", "KH", "SN", "MN", "YE"}

_D0 = Decimal("0")
_D100 = Decimal("100")


class KYBRiskAssessor:
    def __init__(self, app_store: ApplicationStore, ubo_store: UBOStore) -> None:
        self._apps = app_store
        self._ubos = ubo_store

    def assess_risk(self, application_id: str) -> KYBRiskAssessment:
        app = self._apps.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        factors: list[str] = []
        score = _D0

        # Jurisdiction risk
        j = app.jurisdiction.upper()
        if j in _BLOCKED:
            score += Decimal("100")
            factors.append(f"blocked_jurisdiction:{j}")
        elif j in _MEDIUM_RISK:
            score += Decimal("50")
            factors.append(f"medium_risk_jurisdiction:{j}")
        else:
            score += Decimal("10")

        # UBO count
        ubos = self._ubos.list_by_application(application_id)
        if len(ubos) >= 5:
            score += Decimal("15")
            factors.append("high_ubo_count")

        # Business type
        if app.business_type == BusinessType.CHARITY:
            score += Decimal("10")
            factors.append("charity_type")
        elif app.business_type == BusinessType.PLC:
            score -= Decimal("5")

        # Company age
        try:
            submitted = datetime.fromisoformat(app.submitted_at.replace("Z", "+00:00"))
            now = datetime.now(UTC)
            age_days = (now - submitted).days
            if age_days < 365:
                score += Decimal("20")
                factors.append("company_age_lt_1yr")
        except Exception:
            pass

        score = max(_D0, min(_D100, score))
        tier = self.classify_tier(score)
        ts = datetime.now(UTC).isoformat()
        raw = f"{application_id}{ts}".encode()
        assessment_id = f"risk_{hashlib.sha256(raw).hexdigest()[:8]}"
        return KYBRiskAssessment(
            assessment_id=assessment_id,
            application_id=application_id,
            risk_score=score,
            risk_tier=tier,
            factors=factors,
            assessed_at=ts,
        )

    def classify_tier(self, score: Decimal) -> RiskTier:
        if score < Decimal("25"):
            return RiskTier.LOW
        if score < Decimal("50"):
            return RiskTier.MEDIUM
        if score < Decimal("75"):
            return RiskTier.HIGH
        return RiskTier.PROHIBITED

    def get_risk_factors(self, application_id: str) -> list[str]:
        assessment = self.assess_risk(application_id)
        return assessment.factors

    def batch_reassess(self, application_ids: list[str]) -> list[KYBRiskAssessment]:
        results = []
        for aid in application_ids:
            with contextlib.suppress(ValueError):
                results.append(self.assess_risk(aid))
        return results
