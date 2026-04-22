"""Contract test: TOTPService satisfies TwoFactorPort."""

from services.auth.two_factor import TOTPService
from services.auth.two_factor_port import TwoFactorPort


def test_totp_service_satisfies_port():
    svc: TwoFactorPort = TOTPService()
    for method in (
        "setup_totp",
        "confirm_totp",
        "is_enabled",
        "verify_totp",
        "verify_backup_code",
        "revoke_totp",
        "backup_codes_remaining",
    ):
        assert hasattr(svc, method), f"Missing: {method}"
