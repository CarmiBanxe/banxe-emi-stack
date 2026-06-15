"""In-memory TwoFactorPort fake — satisfies the full Protocol contract.

Used by SCAService delegation tests and TwoFactorPort contract tests so that
production code never has to import a stub from a test helper file ad-hoc.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.auth.two_factor import TOTPSetup, VerifyResult


class FakeTwoFactor:
    """Programmable in-memory adapter implementing TwoFactorPort."""

    def __init__(
        self,
        *,
        verify_success: bool = True,
        verify_message: str = "ok",
        backup_success: bool = True,
        enabled_default: bool = True,
    ) -> None:
        self._verify_success = verify_success
        self._verify_message = verify_message
        self._backup_success = backup_success
        self._enabled: dict[str, bool] = {}
        self._enabled_default = enabled_default
        self._backup_count: dict[str, int] = {}
        self.verify_calls: list[tuple[str, str]] = []
        self.confirm_calls: list[tuple[str, str]] = []
        self.revoke_calls: list[str] = []

    def setup_totp(self, customer_id: str, account_name: str | None = None) -> TOTPSetup:
        self._backup_count[customer_id] = 8
        return TOTPSetup(
            customer_id=customer_id,
            secret="JBSWY3DPEHPK3PXP",
            provisioning_uri=f"otpauth://totp/Banxe:{account_name or customer_id}",
            backup_codes=[f"CODE{i:04d}" for i in range(8)],
            created_at=datetime.now(UTC),
        )

    def confirm_totp(self, customer_id: str, otp: str) -> bool:
        self.confirm_calls.append((customer_id, otp))
        if self._verify_success:
            self._enabled[customer_id] = True
        return self._verify_success

    def is_enabled(self, customer_id: str) -> bool:
        return self._enabled.get(customer_id, self._enabled_default)

    def verify_totp(self, customer_id: str, otp: str) -> VerifyResult:
        self.verify_calls.append((customer_id, otp))
        return VerifyResult(success=self._verify_success, message=self._verify_message)

    def verify_backup_code(self, customer_id: str, code: str) -> VerifyResult:
        if self._backup_success and self._backup_count.get(customer_id, 0) > 0:
            self._backup_count[customer_id] -= 1
            return VerifyResult(
                success=True,
                message=f"Backup code accepted. {self._backup_count[customer_id]} remaining.",
            )
        return VerifyResult(success=False, message="Invalid backup code")

    def revoke_totp(self, customer_id: str) -> None:
        self.revoke_calls.append(customer_id)
        self._enabled.pop(customer_id, None)
        self._backup_count.pop(customer_id, None)

    def backup_codes_remaining(self, customer_id: str) -> int:
        return self._backup_count.get(customer_id, 0)
