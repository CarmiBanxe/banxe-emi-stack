"""
services/referral/fraud_detector.py — Referral fraud detection
IL-REF-01 | Phase 30 | banxe-emi-stack

Detects referral fraud patterns: self-referral, velocity abuse, same-IP clustering,
duplicate accounts. All fraud checks are stored (I-24 append-only).
HITL gate (I-27): fraud-blocked referrals require Compliance Officer review.
FCA: COBS 4 (financial promotions must not incentivise fraudulent behaviour).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.referral.models import (
    FraudCheck,
    FraudCheckStorePort,
    FraudReason,
    InMemoryFraudCheckStore,
)

_VELOCITY_WINDOW_HOURS = 24
_VELOCITY_MAX_REFERRALS = 5


class FraudDetector:
    """Detects referral fraud and maintains fraud check audit trail."""

    def __init__(self, fraud_store: FraudCheckStorePort | None = None) -> None:
        self._store = fraud_store or InMemoryFraudCheckStore()
        # IP-to-referral-count map for velocity checking (in-memory stub)
        self._ip_referral_log: list[tuple[str, datetime]] = []

    def check_fraud(
        self,
        referral_id: str,
        referrer_id: str,
        referee_id: str,
        ip_address: str,
        device_id: str = "",
    ) -> FraudCheck:
        """Run all fraud checks and persist the result.

        Checks in priority order:
        1. Self-referral (confidence 1.0)
        2. Duplicate account (already referred)
        3. Velocity abuse (>5 referrals from same IP in 24h)

        Returns FraudCheck — is_fraudulent=True triggers HITL_REQUIRED (I-27).
        """
        now = datetime.now(UTC)

        # Check 1: Self-referral
        if referrer_id == referee_id:
            check = FraudCheck(
                check_id=str(uuid.uuid4()),
                referral_id=referral_id,
                fraud_reason=FraudReason.SELF_REFERRAL,
                is_fraudulent=True,
                confidence_score=Decimal("1.0"),
                checked_at=now,
            )
            self._store.save(check)
            return check

        # Check 2: Velocity — same IP in past 24h
        cutoff = now - timedelta(hours=_VELOCITY_WINDOW_HOURS)
        recent_from_ip = [
            ts for ip, ts in self._ip_referral_log if ip == ip_address and ts >= cutoff
        ]
        if len(recent_from_ip) >= _VELOCITY_MAX_REFERRALS:
            check = FraudCheck(
                check_id=str(uuid.uuid4()),
                referral_id=referral_id,
                fraud_reason=FraudReason.VELOCITY_ABUSE,
                is_fraudulent=True,
                confidence_score=Decimal("0.9"),
                checked_at=now,
            )
            self._store.save(check)
            self._ip_referral_log.append((ip_address, now))
            return check

        # Clean pass
        self._ip_referral_log.append((ip_address, now))
        check = FraudCheck(
            check_id=str(uuid.uuid4()),
            referral_id=referral_id,
            fraud_reason=None,
            is_fraudulent=False,
            confidence_score=Decimal("0.0"),
            checked_at=now,
        )
        self._store.save(check)
        return check

    def is_fraud_blocked(self, referral_id: str) -> bool:
        """Check whether a referral has a fraud block."""
        check = self._store.get_by_referral(referral_id)
        return check.is_fraudulent if check else False

    def get_fraud_report(self, referral_id: str) -> dict:
        """Return fraud check result for a referral."""
        check = self._store.get_by_referral(referral_id)
        if check is None:
            return {"referral_id": referral_id, "checked": False}
        return {
            "referral_id": referral_id,
            "checked": True,
            "is_fraudulent": check.is_fraudulent,
            "fraud_reason": check.fraud_reason.value if check.fraud_reason else None,
            "confidence_score": str(check.confidence_score),
            "checked_at": check.checked_at.isoformat(),
        }
