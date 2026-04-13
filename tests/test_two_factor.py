"""
tests/test_two_factor.py — TOTPService unit tests
S14-03 | banxe-emi-stack

Tests for services/auth/two_factor.py:
  - setup_totp: generates secret, URI, backup codes
  - confirm_totp: activates after first valid OTP
  - verify_totp: validates OTP, rate limiting
  - verify_backup_code: one-time use
  - revoke_totp: clears all state
  - backup_codes_remaining: count after use

Coverage target: 0% → ≥90%
"""

from __future__ import annotations

import pyotp

from services.auth.two_factor import (
    BACKUP_CODE_COUNT,
    MAX_VERIFY_ATTEMPTS,
    TOTP_DIGITS,
    TOTP_INTERVAL,
    TOTPService,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_service_with_active_totp(customer_id: str = "cust-001") -> tuple[TOTPService, str]:
    """Returns (service, secret) with TOTP already active."""
    svc = TOTPService()
    setup = svc.setup_totp(customer_id)
    secret = setup.secret
    otp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).now()
    assert svc.confirm_totp(customer_id, otp) is True
    return svc, secret


# ── setup_totp ─────────────────────────────────────────────────────────────────


def test_setup_totp_returns_secret():
    svc = TOTPService()
    result = svc.setup_totp("cust-setup-01")
    assert result.secret
    assert len(result.secret) > 0


def test_setup_totp_returns_provisioning_uri():
    svc = TOTPService()
    result = svc.setup_totp("cust-setup-02")
    assert result.provisioning_uri.startswith("otpauth://totp/")


def test_setup_totp_returns_backup_codes():
    svc = TOTPService()
    result = svc.setup_totp("cust-setup-03")
    assert len(result.backup_codes) == BACKUP_CODE_COUNT


def test_setup_totp_backup_codes_are_strings():
    svc = TOTPService()
    result = svc.setup_totp("cust-setup-04")
    for code in result.backup_codes:
        assert isinstance(code, str)
        assert len(code) > 0


def test_setup_totp_not_yet_enabled():
    svc = TOTPService()
    svc.setup_totp("cust-setup-05")
    assert svc.is_enabled("cust-setup-05") is False


def test_setup_totp_with_account_name():
    svc = TOTPService()
    result = svc.setup_totp("cust-setup-06", account_name="alice@banxe.com")
    # Email is URL-encoded in the otpauth URI
    assert "alice" in result.provisioning_uri and "banxe.com" in result.provisioning_uri


def test_setup_totp_customer_id_in_result():
    svc = TOTPService()
    result = svc.setup_totp("cust-07")
    assert result.customer_id == "cust-07"


# ── confirm_totp ───────────────────────────────────────────────────────────────


def test_confirm_totp_with_valid_otp_activates():
    svc = TOTPService()
    setup = svc.setup_totp("cust-confirm-01")
    otp = pyotp.TOTP(setup.secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).now()
    assert svc.confirm_totp("cust-confirm-01", otp) is True
    assert svc.is_enabled("cust-confirm-01") is True


def test_confirm_totp_with_invalid_otp_does_not_activate():
    svc = TOTPService()
    svc.setup_totp("cust-confirm-02")
    assert svc.confirm_totp("cust-confirm-02", "000000") is False
    assert svc.is_enabled("cust-confirm-02") is False


def test_confirm_totp_no_setup_returns_false():
    svc = TOTPService()
    assert svc.confirm_totp("cust-no-setup", "123456") is False


# ── verify_totp ────────────────────────────────────────────────────────────────


def test_verify_totp_not_enabled_returns_failure():
    svc = TOTPService()
    svc.setup_totp("cust-disabled")
    result = svc.verify_totp("cust-disabled", "123456")
    assert result.success is False
    assert "not enabled" in result.message


def test_verify_totp_valid_otp_returns_success():
    svc, secret = _make_service_with_active_totp("cust-valid-01")
    otp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).now()
    result = svc.verify_totp("cust-valid-01", otp)
    assert result.success is True
    assert result.message == "OTP verified"


def test_verify_totp_invalid_otp_returns_failure():
    svc, _ = _make_service_with_active_totp("cust-invalid-01")
    result = svc.verify_totp("cust-invalid-01", "000000")
    assert result.success is False
    assert "Invalid OTP" in result.message


def test_verify_totp_invalid_otp_decrements_attempts_remaining():
    svc, _ = _make_service_with_active_totp("cust-attempts-01")
    r1 = svc.verify_totp("cust-attempts-01", "000001")
    r2 = svc.verify_totp("cust-attempts-01", "000002")
    assert r1.attempts_remaining is not None
    assert r2.attempts_remaining is not None
    assert r2.attempts_remaining <= r1.attempts_remaining


def test_verify_totp_rate_limited_after_max_attempts():
    svc, _ = _make_service_with_active_totp("cust-rate-01")
    for _ in range(MAX_VERIFY_ATTEMPTS):
        svc.verify_totp("cust-rate-01", "000000")
    result = svc.verify_totp("cust-rate-01", "000000")
    assert result.success is False
    assert result.attempts_remaining == 0


def test_verify_totp_success_clears_rate_limit():
    svc, secret = _make_service_with_active_totp("cust-clear-01")
    svc.verify_totp("cust-clear-01", "000000")
    svc.verify_totp("cust-clear-01", "000001")
    otp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).now()
    result = svc.verify_totp("cust-clear-01", otp)
    assert result.success is True
    r = svc.verify_totp("cust-clear-01", "000000")
    assert r.attempts_remaining is not None
    assert r.attempts_remaining > 0


def test_verify_totp_unknown_customer_not_enabled():
    svc = TOTPService()
    result = svc.verify_totp("cust-unknown", "123456")
    assert result.success is False


# ── verify_backup_code ─────────────────────────────────────────────────────────


def test_verify_backup_code_valid_code_returns_success():
    svc = TOTPService()
    setup = svc.setup_totp("cust-backup-01")
    code = setup.backup_codes[0]
    result = svc.verify_backup_code("cust-backup-01", code)
    assert result.success is True
    assert "backup code" in result.message.lower()


def test_verify_backup_code_is_one_time_use():
    svc = TOTPService()
    setup = svc.setup_totp("cust-backup-02")
    code = setup.backup_codes[0]
    svc.verify_backup_code("cust-backup-02", code)
    result = svc.verify_backup_code("cust-backup-02", code)
    assert result.success is False


def test_verify_backup_code_decrements_remaining():
    svc = TOTPService()
    setup = svc.setup_totp("cust-backup-03")
    initial = svc.backup_codes_remaining("cust-backup-03")
    svc.verify_backup_code("cust-backup-03", setup.backup_codes[0])
    assert svc.backup_codes_remaining("cust-backup-03") == initial - 1


def test_verify_backup_code_invalid_code():
    svc = TOTPService()
    svc.setup_totp("cust-backup-04")
    result = svc.verify_backup_code("cust-backup-04", "INVALIDCODE")
    assert result.success is False
    assert "Invalid backup code" in result.message


def test_verify_backup_code_case_insensitive():
    svc = TOTPService()
    setup = svc.setup_totp("cust-backup-05")
    code = setup.backup_codes[0]
    result = svc.verify_backup_code("cust-backup-05", code.lower())
    assert result.success is True


def test_verify_backup_code_no_customer_returns_failure():
    svc = TOTPService()
    result = svc.verify_backup_code("cust-nonexistent", "ANYCODE")
    assert result.success is False


# ── revoke_totp ────────────────────────────────────────────────────────────────


def test_revoke_totp_clears_enabled():
    svc, _ = _make_service_with_active_totp("cust-revoke-01")
    assert svc.is_enabled("cust-revoke-01") is True
    svc.revoke_totp("cust-revoke-01")
    assert svc.is_enabled("cust-revoke-01") is False


def test_revoke_totp_clears_backup_codes():
    svc = TOTPService()
    svc.setup_totp("cust-revoke-02")
    assert svc.backup_codes_remaining("cust-revoke-02") == BACKUP_CODE_COUNT
    svc.revoke_totp("cust-revoke-02")
    assert svc.backup_codes_remaining("cust-revoke-02") == 0


def test_revoke_totp_clears_otp_verification():
    svc, _ = _make_service_with_active_totp("cust-revoke-03")
    svc.revoke_totp("cust-revoke-03")
    result = svc.verify_totp("cust-revoke-03", "123456")
    assert result.success is False


def test_revoke_totp_nonexistent_customer_no_error():
    svc = TOTPService()
    svc.revoke_totp("cust-no-such")


# ── backup_codes_remaining ────────────────────────────────────────────────────


def test_backup_codes_remaining_initial_count():
    svc = TOTPService()
    svc.setup_totp("cust-count-01")
    assert svc.backup_codes_remaining("cust-count-01") == BACKUP_CODE_COUNT


def test_backup_codes_remaining_unknown_customer():
    svc = TOTPService()
    assert svc.backup_codes_remaining("cust-unknown-count") == 0


# ── is_enabled ────────────────────────────────────────────────────────────────


def test_is_enabled_false_before_confirm():
    svc = TOTPService()
    assert svc.is_enabled("cust-never-setup") is False
