"""Additional TOTPService tests — close residual missing lines + Protocol contract.

Targets services/auth/two_factor.py missing branches:
  - lines 100-101: setup_totp ImportError fallback when pyotp missing
  - lines 209-210: _do_verify_totp ImportError fallback when pyotp missing

Also exercises TwoFactorPort Protocol contract via the in-memory fake adapter
(tests/_fakes/two_factor_fake.py) — proves duck-typing structural compliance
and confirms drop-in usage in SCAService.
"""

from __future__ import annotations

import sys

import pytest

from services.auth.sca_service import SCAService
from services.auth.two_factor import (
    BACKUP_CODE_COUNT,
    TOTPService,
    VerifyResult,
)
from services.auth.two_factor_port import TwoFactorPort
from tests._fakes.two_factor_fake import FakeTwoFactor

# ── two_factor.py lines 100-101: setup_totp ImportError fallback ─────────────


def test_setup_totp_raises_importerror_when_pyotp_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyotp", None)

    svc = TOTPService()

    with pytest.raises(ImportError, match="pip install pyotp"):
        svc.setup_totp("cust-no-pyotp")


# ── two_factor.py lines 209-210: _do_verify_totp ImportError fallback ────────


def test_verify_totp_returns_failure_when_pyotp_missing(monkeypatch):
    """If pyotp disappears between setup and verify, verify must return
    success=False (not raise) so the caller path stays stable."""
    svc = TOTPService()
    setup = svc.setup_totp("cust-pyotp-vanishes")  # uses real pyotp here
    svc._enabled[setup.customer_id] = True

    monkeypatch.setitem(sys.modules, "pyotp", None)

    result = svc.verify_totp(setup.customer_id, "000000")

    assert isinstance(result, VerifyResult)
    assert result.success is False


def test_confirm_totp_returns_false_when_pyotp_missing(monkeypatch):
    """confirm_totp delegates to _do_verify_totp; ImportError path must
    surface as bool=False, not exception."""
    svc = TOTPService()
    setup = svc.setup_totp("cust-confirm-no-pyotp")

    monkeypatch.setitem(sys.modules, "pyotp", None)

    assert svc.confirm_totp(setup.customer_id, "000000") is False
    assert svc.is_enabled(setup.customer_id) is False


# ── Boundary: backup-code one-time-use semantics ─────────────────────────────


def test_backup_code_consumed_on_use():
    svc = TOTPService()
    setup = svc.setup_totp("cust-backup")
    assert svc.backup_codes_remaining("cust-backup") == BACKUP_CODE_COUNT

    first_code = setup.backup_codes[0]
    result = svc.verify_backup_code("cust-backup", first_code)

    assert result.success is True
    assert svc.backup_codes_remaining("cust-backup") == BACKUP_CODE_COUNT - 1

    # Second use of same code must fail (consumed)
    second = svc.verify_backup_code("cust-backup", first_code)
    assert second.success is False


def test_backup_code_case_insensitive():
    svc = TOTPService()
    setup = svc.setup_totp("cust-case")
    code = setup.backup_codes[0]

    # Codes are uppercased in storage; lower-cased input must still match
    result = svc.verify_backup_code("cust-case", code.lower())
    assert result.success is True


def test_backup_code_unknown_customer_returns_failure():
    svc = TOTPService()
    result = svc.verify_backup_code("nobody", "DEADBEEF")
    assert result.success is False
    assert result.message == "Invalid backup code"


def test_revoke_totp_clears_all_state():
    svc = TOTPService()
    svc.setup_totp("cust-revoke")
    svc._enabled["cust-revoke"] = True

    svc.revoke_totp("cust-revoke")

    assert svc.is_enabled("cust-revoke") is False
    assert svc.backup_codes_remaining("cust-revoke") == 0
    assert "cust-revoke" not in svc._secrets


def test_revoke_totp_idempotent_for_unknown_customer():
    svc = TOTPService()
    svc.revoke_totp("never-existed")  # must not raise
    assert svc.is_enabled("never-existed") is False


# ── TwoFactorPort Protocol contract via FakeTwoFactor ────────────────────────


def test_fake_two_factor_satisfies_port_protocol():
    fake: TwoFactorPort = FakeTwoFactor()
    for method in (
        "setup_totp",
        "confirm_totp",
        "is_enabled",
        "verify_totp",
        "verify_backup_code",
        "revoke_totp",
        "backup_codes_remaining",
    ):
        assert callable(getattr(fake, method)), f"FakeTwoFactor missing: {method}"


def test_fake_two_factor_drop_in_replaces_totp_service_in_sca():
    fake = FakeTwoFactor(verify_success=True)
    sca = SCAService(two_factor=fake)

    challenge = sca.create_challenge(
        customer_id="cust-fake",
        transaction_id="txn-fake-1",
        method="otp",
    )
    result = sca.verify(challenge_id=challenge.challenge_id, otp_code="123456")

    assert result.verified is True
    assert fake.verify_calls == [("cust-fake", "123456")]


def test_fake_two_factor_negative_path_propagates_to_sca_verify_failure():
    fake = FakeTwoFactor(verify_success=False, verify_message="bad otp")
    sca = SCAService(two_factor=fake)

    challenge = sca.create_challenge(
        customer_id="cust-fake-neg",
        transaction_id="txn-fake-neg",
        method="otp",
    )
    result = sca.verify(challenge_id=challenge.challenge_id, otp_code="999999")

    assert result.verified is False
    assert result.attempts_remaining == 4


def test_fake_two_factor_setup_and_revoke_round_trip():
    fake = FakeTwoFactor()
    setup = fake.setup_totp("cust-rt", account_name="Round Trip")

    assert setup.customer_id == "cust-rt"
    assert setup.provisioning_uri.endswith("Round Trip")
    assert fake.backup_codes_remaining("cust-rt") == 8

    fake.revoke_totp("cust-rt")
    assert fake.backup_codes_remaining("cust-rt") == 0
    assert fake.revoke_calls == ["cust-rt"]


def test_fake_two_factor_confirm_marks_enabled():
    fake = FakeTwoFactor(verify_success=True)
    fake.setup_totp("cust-confirm")

    assert fake.confirm_totp("cust-confirm", "000000") is True
    assert fake.is_enabled("cust-confirm") is True
