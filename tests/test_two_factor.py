"""
test_two_factor.py — Lightweight 2FA (TOTP + backup codes) tests
S17-04: 2FA/MFA — RFC 6238 TOTP, PSR 2017 Reg.71 (SCA)
"""
from __future__ import annotations

import pytest

pyotp = pytest.importorskip("pyotp", reason="pyotp not installed")

from services.auth.two_factor import TOTPService


@pytest.fixture
def svc():
    return TOTPService()


@pytest.fixture
def setup(svc):
    return svc.setup_totp("cust-001", account_name="alice@banxe.com")


@pytest.fixture
def active_svc(svc, setup):
    """Service with TOTP confirmed (activated)."""
    totp = pyotp.TOTP(setup.secret)
    svc.confirm_totp("cust-001", totp.now())
    return svc, setup


# ── Setup ──────────────────────────────────────────────────────────────────────

class TestSetup:
    def test_returns_setup(self, svc):
        setup = svc.setup_totp("cust-001")
        assert setup.customer_id == "cust-001"

    def test_secret_is_base32(self, svc):
        import base64
        setup = svc.setup_totp("cust-001")
        # pyotp secrets are valid base32
        base64.b32decode(setup.secret)

    def test_provisioning_uri_format(self, setup):
        assert setup.provisioning_uri.startswith("otpauth://totp/")
        assert "Banxe" in setup.provisioning_uri

    def test_backup_codes_count(self, setup):
        assert len(setup.backup_codes) == 8

    def test_backup_codes_uppercase_hex(self, setup):
        for code in setup.backup_codes:
            assert code == code.upper()
            assert len(code) == 8

    def test_not_enabled_before_confirm(self, svc, setup):
        assert not svc.is_enabled("cust-001")

    def test_enabled_after_confirm(self, active_svc):
        svc, setup = active_svc
        assert svc.is_enabled("cust-001")


# ── TOTP verification ──────────────────────────────────────────────────────────

class TestVerifyTOTP:
    def test_valid_otp_accepted(self, active_svc):
        svc, setup = active_svc
        totp = pyotp.TOTP(setup.secret)
        result = svc.verify_totp("cust-001", totp.now())
        assert result.success is True

    def test_invalid_otp_rejected(self, active_svc):
        svc, _ = active_svc
        result = svc.verify_totp("cust-001", "000000")
        assert result.success is False

    def test_invalid_otp_decrements_attempts(self, active_svc):
        svc, _ = active_svc
        result = svc.verify_totp("cust-001", "000000")
        assert result.attempts_remaining is not None
        assert result.attempts_remaining < 5

    def test_not_enabled_returns_error(self, svc):
        result = svc.verify_totp("cust-999", "123456")
        assert result.success is False
        assert "not enabled" in result.message

    def test_successful_verify_clears_attempts(self, active_svc):
        svc, setup = active_svc
        # Make a failed attempt
        svc.verify_totp("cust-001", "000000")
        # Now verify with correct OTP
        totp = pyotp.TOTP(setup.secret)
        result = svc.verify_totp("cust-001", totp.now())
        assert result.success is True


# ── Backup codes ───────────────────────────────────────────────────────────────

class TestBackupCodes:
    def test_backup_code_accepted(self, active_svc):
        svc, setup = active_svc
        result = svc.verify_backup_code("cust-001", setup.backup_codes[0])
        assert result.success is True

    def test_backup_code_consumed_after_use(self, active_svc):
        svc, setup = active_svc
        code = setup.backup_codes[0]
        svc.verify_backup_code("cust-001", code)
        # Second use fails
        result = svc.verify_backup_code("cust-001", code)
        assert result.success is False

    def test_remaining_count_decrements(self, active_svc):
        svc, setup = active_svc
        assert svc.backup_codes_remaining("cust-001") == 8
        svc.verify_backup_code("cust-001", setup.backup_codes[0])
        assert svc.backup_codes_remaining("cust-001") == 7

    def test_invalid_backup_code_rejected(self, active_svc):
        svc, _ = active_svc
        result = svc.verify_backup_code("cust-001", "INVALID1")
        assert result.success is False

    def test_remaining_shown_in_message(self, active_svc):
        svc, setup = active_svc
        result = svc.verify_backup_code("cust-001", setup.backup_codes[0])
        assert "7" in result.message


# ── Revoke ────────────────────────────────────────────────────────────────────

class TestRevoke:
    def test_revoke_disables_totp(self, active_svc):
        svc, setup = active_svc
        svc.revoke_totp("cust-001")
        assert not svc.is_enabled("cust-001")

    def test_verify_fails_after_revoke(self, active_svc):
        svc, setup = active_svc
        svc.revoke_totp("cust-001")
        result = svc.verify_totp("cust-001", "123456")
        assert result.success is False

    def test_revoke_idempotent(self, svc):
        svc.revoke_totp("never-existed")  # Should not raise


# ── Customer DTO extension (IL-036) ───────────────────────────────────────────

class TestCustomerDTOExtended:
    """Smoke tests for extended IndividualProfile fields (IL-036)."""

    def test_individual_full_name_with_title(self):
        from datetime import date
        from services.customer.customer_port import Address, IndividualProfile
        profile = IndividualProfile(
            first_name="Alice",
            last_name="Smith",
            date_of_birth=date(1990, 5, 15),
            nationality="GB",
            address=Address(line1="1 High St", city="London", country="GB"),
            title="Dr",
            middle_name="Jane",
        )
        assert profile.full_name == "Dr Alice Jane Smith"

    def test_individual_fatca_crs_defaults(self):
        from datetime import date
        from services.customer.customer_port import Address, IndividualProfile
        profile = IndividualProfile(
            first_name="Bob",
            last_name="Jones",
            date_of_birth=date(1985, 3, 1),
            nationality="GB",
            address=Address(line1="2 Low St", city="Manchester", country="GB"),
        )
        assert profile.fatca_us_person is False
        assert profile.crs_tax_residencies == []
        assert profile.preferred_language == "EN"

    def test_company_extended_fields(self):
        from datetime import date
        from services.customer.customer_port import Address, CompanyProfile
        company = CompanyProfile(
            company_name="Acme Ltd",
            registration_number="12345678",
            country_of_incorporation="GB",
            registered_address=Address(line1="1 Corp St", city="London", country="GB"),
            company_type="Ltd",
            industry="Fintech",
            tax_id="UTR1234567890",
            date_of_registration=date(2020, 1, 15),
        )
        assert company.company_type == "Ltd"
        assert company.tax_id == "UTR1234567890"
