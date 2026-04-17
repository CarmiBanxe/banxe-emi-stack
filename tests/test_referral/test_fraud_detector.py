"""
tests/test_referral/test_fraud_detector.py — Unit tests for FraudDetector
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.referral.fraud_detector import (
    _VELOCITY_MAX_REFERRALS,
    _VELOCITY_WINDOW_HOURS,
    FraudDetector,
)
from services.referral.models import FraudReason, InMemoryFraudCheckStore


@pytest.fixture()
def detector() -> FraudDetector:
    return FraudDetector()


# ── check_fraud — self-referral ────────────────────────────────────────────


def test_check_fraud_self_referral_is_fraudulent(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="ref-1",
        referrer_id="cust-1",
        referee_id="cust-1",  # same as referrer
        ip_address="1.2.3.4",
    )
    assert check.is_fraudulent is True


def test_check_fraud_self_referral_reason(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="ref-2",
        referrer_id="cust-2",
        referee_id="cust-2",
        ip_address="1.2.3.4",
    )
    assert check.fraud_reason == FraudReason.SELF_REFERRAL


def test_check_fraud_self_referral_confidence_is_1(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="ref-3",
        referrer_id="cust-3",
        referee_id="cust-3",
        ip_address="1.2.3.4",
    )
    assert check.confidence_score == Decimal("1.0")


# ── check_fraud — velocity abuse ───────────────────────────────────────────


def test_check_fraud_velocity_abuse_after_max_referrals() -> None:
    detector = FraudDetector()
    ip = "10.0.0.1"
    # Create exactly _VELOCITY_MAX_REFERRALS clean referrals from same IP
    for i in range(_VELOCITY_MAX_REFERRALS):
        detector.check_fraud(
            referral_id=f"clean-ref-{i}",
            referrer_id=f"referrer-{i}",
            referee_id=f"referee-{i}",
            ip_address=ip,
        )
    # Next one should trigger velocity abuse
    check = detector.check_fraud(
        referral_id="abuse-ref",
        referrer_id="referrer-x",
        referee_id="referee-x",
        ip_address=ip,
    )
    assert check.is_fraudulent is True
    assert check.fraud_reason == FraudReason.VELOCITY_ABUSE


def test_check_fraud_velocity_abuse_confidence_is_09() -> None:
    detector = FraudDetector()
    ip = "10.0.0.2"
    for i in range(_VELOCITY_MAX_REFERRALS):
        detector.check_fraud(
            referral_id=f"v-clean-{i}",
            referrer_id=f"vr-{i}",
            referee_id=f"ve-{i}",
            ip_address=ip,
        )
    check = detector.check_fraud(
        referral_id="v-abuse",
        referrer_id="vr-x",
        referee_id="ve-x",
        ip_address=ip,
    )
    assert check.confidence_score == Decimal("0.9")


# ── check_fraud — clean pass ───────────────────────────────────────────────


def test_check_fraud_clean_pass_not_fraudulent(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="clean-ref-1",
        referrer_id="clean-referrer",
        referee_id="clean-referee",
        ip_address="192.168.1.1",
    )
    assert check.is_fraudulent is False


def test_check_fraud_clean_pass_zero_confidence(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="clean-ref-2",
        referrer_id="clean-r1",
        referee_id="clean-r2",
        ip_address="192.168.1.2",
    )
    assert check.confidence_score == Decimal("0.0")


def test_check_fraud_clean_pass_no_reason(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="clean-ref-3",
        referrer_id="r1",
        referee_id="r2",
        ip_address="192.168.1.3",
    )
    assert check.fraud_reason is None


def test_check_fraud_clean_pass_has_referral_id(detector: FraudDetector) -> None:
    check = detector.check_fraud(
        referral_id="check-ref-id",
        referrer_id="r3",
        referee_id="r4",
        ip_address="192.168.1.4",
    )
    assert check.referral_id == "check-ref-id"


def test_check_fraud_persists_to_store() -> None:
    store = InMemoryFraudCheckStore()
    det = FraudDetector(fraud_store=store)
    det.check_fraud(
        referral_id="persist-ref",
        referrer_id="p1",
        referee_id="p2",
        ip_address="1.1.1.1",
    )
    assert store.get_by_referral("persist-ref") is not None


# ── is_fraud_blocked ───────────────────────────────────────────────────────


def test_is_fraud_blocked_true_for_fraudulent_referral(detector: FraudDetector) -> None:
    detector.check_fraud(
        referral_id="blocked-ref",
        referrer_id="same",
        referee_id="same",
        ip_address="1.2.3.4",
    )
    assert detector.is_fraud_blocked("blocked-ref") is True


def test_is_fraud_blocked_false_for_clean_referral(detector: FraudDetector) -> None:
    detector.check_fraud(
        referral_id="clean-ref",
        referrer_id="r-a",
        referee_id="r-b",
        ip_address="5.6.7.8",
    )
    assert detector.is_fraud_blocked("clean-ref") is False


def test_is_fraud_blocked_false_when_no_check_exists(detector: FraudDetector) -> None:
    assert detector.is_fraud_blocked("no-check-ref") is False


# ── get_fraud_report ───────────────────────────────────────────────────────


def test_get_fraud_report_unchecked_referral(detector: FraudDetector) -> None:
    result = detector.get_fraud_report("no-check-ref-2")
    assert result["checked"] is False


def test_get_fraud_report_after_fraud_check(detector: FraudDetector) -> None:
    detector.check_fraud(
        referral_id="report-ref",
        referrer_id="same-id",
        referee_id="same-id",
        ip_address="1.2.3.4",
    )
    result = detector.get_fraud_report("report-ref")
    assert result["checked"] is True
    assert result["is_fraudulent"] is True
    assert result["fraud_reason"] == "SELF_REFERRAL"


def test_get_fraud_report_clean_referral(detector: FraudDetector) -> None:
    detector.check_fraud(
        referral_id="clean-report",
        referrer_id="r-c",
        referee_id="r-d",
        ip_address="9.9.9.9",
    )
    result = detector.get_fraud_report("clean-report")
    assert result["is_fraudulent"] is False
    assert result["fraud_reason"] is None


# ── velocity constants ─────────────────────────────────────────────────────


def test_velocity_window_is_24_hours() -> None:
    assert _VELOCITY_WINDOW_HOURS == 24


def test_velocity_max_referrals_is_5() -> None:
    assert _VELOCITY_MAX_REFERRALS == 5
