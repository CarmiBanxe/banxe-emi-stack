"""
tests/test_sca_service_edge.py — SCA service edge cases
S15-FIX-2 | PSD2 Art.97 | banxe-emi-stack

15 tests: expired challenge, replay attack, concurrent verify, invalid method,
brute force lockout, resend on used challenge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.auth.sca_service import (
    SCA_MAX_ATTEMPTS,
    SCA_MAX_RESENDS,
    InMemorySCAStore,
    SCAService,
)


@pytest.fixture
def svc() -> SCAService:
    return SCAService(store=InMemorySCAStore())


class TestSCAExpiredChallenge:
    def test_expired_challenge_returns_not_verified(self, svc):
        ch = svc.create_challenge("cust-exp", "txn-exp", "otp")
        # Artificially expire
        ch.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
        svc._store.save(ch)
        result = svc.verify(ch.challenge_id, otp_code="123456")
        assert result.verified is False
        assert result.error == "Challenge expired"

    def test_expired_challenge_status_updated(self, svc):
        ch = svc.create_challenge("cust-exp2", "txn-exp2", "otp")
        ch.expires_at = datetime.now(tz=UTC) - timedelta(seconds=5)
        svc._store.save(ch)
        svc.verify(ch.challenge_id, otp_code="111111")
        updated = svc._store.get(ch.challenge_id)
        assert updated.status == "expired"


class TestSCAReplayAttack:
    def test_verified_challenge_cannot_be_reused(self, svc):
        ch = svc.create_challenge("cust-replay", "txn-replay", "biometric")
        svc.verify(ch.challenge_id, biometric_proof="biometric:approved:test")
        result = svc.verify(ch.challenge_id, biometric_proof="biometric:approved:test")
        assert result.verified is False
        assert result.error == "Challenge already used"

    def test_used_challenge_status_persisted(self, svc):
        ch = svc.create_challenge("cust-replay2", "txn-replay2", "biometric")
        svc.verify(ch.challenge_id, biometric_proof="biometric:approved:test")
        stored = svc._store.get(ch.challenge_id)
        assert stored.status == "used"


class TestSCABruteForce:
    def test_five_failures_lock_challenge(self, svc):
        ch = svc.create_challenge("cust-bf", "txn-bf", "biometric")
        for _ in range(SCA_MAX_ATTEMPTS):
            svc.verify(ch.challenge_id, biometric_proof="wrong-proof")
        result = svc.verify(ch.challenge_id, biometric_proof="biometric:approved:should-fail")
        assert result.verified is False
        assert result.attempts_remaining == 0

    def test_failed_challenge_status_set(self, svc):
        ch = svc.create_challenge("cust-bf2", "txn-bf2", "biometric")
        for _ in range(SCA_MAX_ATTEMPTS):
            svc.verify(ch.challenge_id, biometric_proof="wrong")
        stored = svc._store.get(ch.challenge_id)
        assert stored.status == "failed"

    def test_attempts_remaining_decrements(self, svc):
        ch = svc.create_challenge("cust-bf3", "txn-bf3", "biometric")
        r1 = svc.verify(ch.challenge_id, biometric_proof="bad1")
        r2 = svc.verify(ch.challenge_id, biometric_proof="bad2")
        assert r2.attempts_remaining < r1.attempts_remaining


class TestSCAInvalidMethod:
    def test_invalid_method_raises(self, svc):
        with pytest.raises(ValueError, match="Unsupported SCA method"):
            svc.create_challenge("cust-m", "txn-m", "sms")

    def test_only_otp_and_biometric_accepted(self, svc):
        # OTP accepted
        ch1 = svc.create_challenge("cust-ok1", "txn-ok1", "otp")
        assert ch1.method == "otp"
        # Biometric accepted
        ch2 = svc.create_challenge("cust-ok2", "txn-ok2", "biometric")
        assert ch2.method == "biometric"


class TestSCAConcurrentLimit:
    def test_three_active_challenges_allowed(self, svc):
        for i in range(3):
            svc.create_challenge("cust-conc", f"txn-conc-{i}", "otp")

    def test_fourth_active_challenge_raises(self, svc):
        for i in range(3):
            svc.create_challenge("cust-conc4", f"txn-conc4-{i}", "otp")
        with pytest.raises(RuntimeError, match="active SCA challenges"):
            svc.create_challenge("cust-conc4", "txn-conc4-extra", "otp")


class TestSCAResendEdgeCases:
    def test_resend_used_challenge_raises(self, svc):
        ch = svc.create_challenge("cust-resend-u", "txn-resend-u", "biometric")
        svc.verify(ch.challenge_id, biometric_proof="biometric:approved:ok")
        with pytest.raises(ValueError, match="used"):
            svc.resend_challenge(ch.challenge_id)

    def test_resend_failed_challenge_raises(self, svc):
        ch = svc.create_challenge("cust-resend-f", "txn-resend-f", "biometric")
        for _ in range(SCA_MAX_ATTEMPTS):
            svc.verify(ch.challenge_id, biometric_proof="bad")
        with pytest.raises(ValueError, match="failed"):
            svc.resend_challenge(ch.challenge_id)

    def test_resend_nonexistent_raises_key_error(self, svc):
        with pytest.raises(KeyError):
            svc.resend_challenge("does-not-exist")

    def test_resend_extends_expiry(self, svc):
        ch = svc.create_challenge("cust-resend-ext", "txn-ext", "otp")
        original_expiry = ch.expires_at
        svc.resend_challenge(ch.challenge_id)
        updated = svc._store.get(ch.challenge_id)
        assert updated.expires_at >= original_expiry

    def test_resend_max_limit_enforced(self, svc):
        ch = svc.create_challenge("cust-resend-lim", "txn-lim", "otp")
        for _ in range(SCA_MAX_RESENDS):
            svc.resend_challenge(ch.challenge_id)
        with pytest.raises(ValueError, match="limit"):
            svc.resend_challenge(ch.challenge_id)
