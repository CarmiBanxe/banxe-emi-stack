"""Extended SCA service tests — close residual missing lines.

Targets services/auth/sca_service.py missing branches:
  - InMemorySCAStore.delete (line 90) — boundary cleanup path
  - _verify_otp ImportError fallback for pyotp (lines 353-357) — port-fallback

Canon: ADR-015 ports/adapters; tests must not touch service code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sys

import pytest

from services.auth.sca_models import SCAChallenge
from services.auth.sca_service import InMemorySCAStore, SCAService


def _make_pending_challenge(
    *,
    customer_id: str = "cust-test",
    method: str = "otp",
    challenge_id: str = "chal-extended-1",
) -> SCAChallenge:
    now = datetime.now(tz=UTC)
    return SCAChallenge(
        challenge_id=challenge_id,
        customer_id=customer_id,
        transaction_id="txn-extended-1",
        method=method,
        status="pending",
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )


# ── InMemorySCAStore.delete (line 90) ────────────────────────────────────────


def test_inmemory_store_delete_removes_existing_challenge():
    store = InMemorySCAStore()
    challenge = _make_pending_challenge()
    store.save(challenge)
    assert store.get(challenge.challenge_id) is challenge

    store.delete(challenge.challenge_id)

    assert store.get(challenge.challenge_id) is None
    assert store.count_active_for_customer(challenge.customer_id) == 0


def test_inmemory_store_delete_unknown_challenge_is_silent():
    """delete must be idempotent — pop(..., None) guarantees no KeyError."""
    store = InMemorySCAStore()
    store.delete("does-not-exist")
    assert store.get("does-not-exist") is None


# ── _verify_otp pyotp ImportError fallback (lines 353-357) ───────────────────


def test_verify_otp_pyotp_missing_falls_back_to_test_hook(monkeypatch):
    """When pyotp is unavailable AND no TwoFactorPort wired, the legacy
    deterministic fixture accepts only otp_code='000000' for customers whose
    id ends with '-test'. This is the documented fallback path."""
    monkeypatch.setitem(sys.modules, "pyotp", None)

    svc = SCAService()  # no two_factor port → exercises pyotp branch
    challenge = svc.create_challenge(
        customer_id="cust-test",
        transaction_id="txn-pyotp-fallback",
        method="otp",
    )

    result = svc.verify(challenge_id=challenge.challenge_id, otp_code="000000")

    assert result.verified is True
    assert result.transaction_id == "txn-pyotp-fallback"
    assert result.sca_token  # JWT issued via JwtScaTokenIssuer


def test_verify_otp_pyotp_missing_rejects_non_test_customer(monkeypatch):
    """Fallback hook requires customer_id endswith '-test' — otherwise reject."""
    monkeypatch.setitem(sys.modules, "pyotp", None)

    svc = SCAService()
    challenge = svc.create_challenge(
        customer_id="cust-prod",  # does not end with -test
        transaction_id="txn-pyotp-reject",
        method="otp",
    )

    result = svc.verify(challenge_id=challenge.challenge_id, otp_code="000000")

    assert result.verified is False
    assert result.error == "Invalid OTP or biometric proof"


def test_verify_otp_pyotp_missing_rejects_wrong_code(monkeypatch):
    """Even for -test customers, only '000000' passes the fallback hook."""
    monkeypatch.setitem(sys.modules, "pyotp", None)

    svc = SCAService()
    challenge = svc.create_challenge(
        customer_id="cust-test",
        transaction_id="txn-pyotp-wrong",
        method="otp",
    )

    result = svc.verify(challenge_id=challenge.challenge_id, otp_code="123456")

    assert result.verified is False
    assert result.attempts_remaining == 4


@pytest.mark.parametrize(
    "active_state",
    [
        "expired",
        "used",
    ],
)
def test_inmemory_store_active_filter_excludes_non_pending(active_state):
    """count_active_for_customer must filter by status=='pending' only."""
    store = InMemorySCAStore()
    challenge = _make_pending_challenge(challenge_id=f"chal-{active_state}")
    challenge.status = active_state
    store.save(challenge)

    assert store.count_active_for_customer(challenge.customer_id) == 0
