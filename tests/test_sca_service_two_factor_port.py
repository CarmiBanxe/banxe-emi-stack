"""Tests for TwoFactorPort delegate-path in SCAService._verify_otp.

Sprint 4 Track A Block 6 — closes NEXT_SESSION_START.md Task 4:
"Wire services/auth/two_factor_port.py (currently 0% coverage) to
services/auth/two_factor.py::TOTPService".

Covers both branches of SCAService._verify_otp:
  - Production path: SCAService(two_factor=...) delegates to TwoFactorPort.
  - Legacy path: SCAService() (no two_factor) falls back to the
    pyotp/deterministic fixture (backward-compat with existing test contour).

PSD2 RTS Art.10 dynamic linking + Art.4(30) two-factor (knowledge + possession).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.auth.sca_models import SCAChallenge
from services.auth.sca_service import SCAService
from services.auth.two_factor import TOTPSetup, VerifyResult
from services.auth.two_factor_port import TwoFactorPort


class StubTwoFactor:
    """In-memory TwoFactorPort stub for SCAService delegation tests."""

    def __init__(self, success: bool = True, message: str = "ok") -> None:
        self._success = success
        self._message = message
        self.calls: list[tuple[str, str]] = []

    def setup_totp(self, customer_id: str, account_name: str | None = None) -> TOTPSetup:
        raise NotImplementedError

    def confirm_totp(self, customer_id: str, otp: str) -> bool:
        raise NotImplementedError

    def is_enabled(self, customer_id: str) -> bool:
        raise NotImplementedError

    def verify_totp(self, customer_id: str, otp: str) -> VerifyResult:
        self.calls.append((customer_id, otp))
        return VerifyResult(success=self._success, message=self._message)

    def verify_backup_code(self, customer_id: str, code: str) -> VerifyResult:
        raise NotImplementedError

    def revoke_totp(self, customer_id: str) -> None:
        raise NotImplementedError

    def backup_codes_remaining(self, customer_id: str) -> int:
        raise NotImplementedError


def _make_challenge(
    customer_id: str = "cust-001",
    method: str = "otp",
    transaction_id: str = "txn-001",
) -> SCAChallenge:
    """Build a minimal pending SCAChallenge for unit-level tests."""
    now = datetime.now(tz=UTC)
    return SCAChallenge(
        challenge_id="ch-001",
        customer_id=customer_id,
        transaction_id=transaction_id,
        method=method,
        status="pending",
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )


def test_verify_otp_delegates_when_two_factor_provided() -> None:
    """SCAService(two_factor=stub) routes _verify_otp to the port and returns True."""
    stub = StubTwoFactor(success=True)
    svc = SCAService(two_factor=stub)
    challenge = _make_challenge(customer_id="cust-42")

    result = svc._verify_otp(challenge, "123456")

    assert result is True
    assert len(stub.calls) == 1
    assert stub.calls[0] == ("cust-42", "123456")


def test_verify_otp_returns_false_when_two_factor_fails() -> None:
    """Failed VerifyResult from the port → _verify_otp returns False."""
    stub = StubTwoFactor(success=False, message="invalid otp")
    svc = SCAService(two_factor=stub)
    challenge = _make_challenge()

    result = svc._verify_otp(challenge, "999999")

    assert result is False
    assert len(stub.calls) == 1


def test_verify_otp_falls_back_to_legacy_when_two_factor_none() -> None:
    """SCAService() with no two_factor uses the legacy pyotp/deterministic path."""
    svc = SCAService()
    assert svc._two_factor is None

    challenge = _make_challenge(customer_id="cust-legacy")
    result = svc._verify_otp(challenge, "000000")

    assert isinstance(result, bool)


def test_verify_otp_strips_whitespace_before_delegate() -> None:
    """Production path strips whitespace from otp_code before delegating."""
    stub = StubTwoFactor(success=True)
    svc = SCAService(two_factor=stub)
    challenge = _make_challenge()

    svc._verify_otp(challenge, "  123456  ")

    assert len(stub.calls) == 1
    assert stub.calls[0] == (challenge.customer_id, "123456")


def test_constructor_accepts_optional_two_factor_kwarg() -> None:
    """Backward-compat: SCAService() still constructs without two_factor."""
    svc_default = SCAService()
    assert svc_default._two_factor is None

    svc_explicit_none = SCAService(two_factor=None)
    assert svc_explicit_none._two_factor is None

    stub = StubTwoFactor()
    port: TwoFactorPort = stub
    svc_with_port = SCAService(two_factor=port)
    assert svc_with_port._two_factor is stub
