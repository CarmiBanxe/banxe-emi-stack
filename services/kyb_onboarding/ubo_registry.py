from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.kyb_onboarding.models import (
    UBOStore,
    UBOVerification,
    UltimateBeneficialOwner,
)

UBO_THRESHOLD_PCT = Decimal("25")  # I-01
BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
FATF_GREYLIST = {
    "PK",
    "AE",
    "JO",
    "TN",
    "VN",
    "LK",
    "NG",
    "ET",
    "KH",
    "MM",
    "SN",
    "MN",
    "YE",
}


class UBORegistry:
    def __init__(self, ubo_store: UBOStore) -> None:
        self._ubos = ubo_store

    def register_ubo(
        self,
        application_id: str,
        full_name: str,
        nationality: str,
        dob: str,
        ownership_pct: Decimal,  # I-01
        is_psc: bool = False,
    ) -> UltimateBeneficialOwner:
        if is_psc and ownership_pct < UBO_THRESHOLD_PCT:
            raise ValueError(
                f"I-01: PSC requires ownership_pct >= {UBO_THRESHOLD_PCT}, got {ownership_pct}"
            )
        ts = datetime.now(UTC).isoformat()
        raw = f"{application_id}{full_name}{ts}".encode()
        ubo_id = f"ubo_{hashlib.sha256(raw).hexdigest()[:8]}"
        ubo = UltimateBeneficialOwner(
            ubo_id=ubo_id,
            application_id=application_id,
            full_name=full_name,
            nationality=nationality.upper(),
            date_of_birth=dob,
            ownership_pct=ownership_pct,
            verification_status=UBOVerification.PENDING,
            is_psc=is_psc,
        )
        self._ubos.save(ubo)
        return ubo

    def verify_identity(self, ubo_id: str, verification_ref: str) -> UltimateBeneficialOwner:
        """Stub: sets status to VERIFIED (Companies House PSC API placeholder, BT-002)."""
        ubo = self._ubos.get(ubo_id)
        if ubo is None:
            raise ValueError(f"UBO {ubo_id} not found")
        verified = UltimateBeneficialOwner(
            ubo_id=ubo.ubo_id,
            application_id=ubo.application_id,
            full_name=ubo.full_name,
            nationality=ubo.nationality,
            date_of_birth=ubo.date_of_birth,
            ownership_pct=ubo.ownership_pct,
            verification_status=UBOVerification.VERIFIED,
            is_psc=ubo.is_psc,
        )
        self._ubos.save(verified)
        return verified

    def screen_sanctions(self, ubo_id: str) -> tuple[bool, str]:
        """I-02: nationality in BLOCKED_JURISDICTIONS → (False, 'blocked_jurisdiction').
        I-03: nationality in FATF_GREYLIST → (True, 'edd_required')."""
        ubo = self._ubos.get(ubo_id)
        if ubo is None:
            return False, "ubo_not_found"
        if ubo.nationality in BLOCKED_JURISDICTIONS:
            return False, "blocked_jurisdiction"
        if ubo.nationality in FATF_GREYLIST:
            return True, "edd_required"
        return True, "clear"

    def get_ubos_for_business(self, application_id: str) -> list[UltimateBeneficialOwner]:
        return self._ubos.list_by_application(application_id)

    def calculate_control_percentage(self, application_id: str) -> Decimal:
        """I-01: sum of ownership_pct as Decimal."""
        ubos = self._ubos.list_by_application(application_id)
        return sum((u.ownership_pct for u in ubos), Decimal("0"))
