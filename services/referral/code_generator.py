"""
services/referral/code_generator.py — Referral code generation
IL-REF-01 | Phase 30 | banxe-emi-stack

Generates unique 8-character alphanumeric referral codes.
Supports vanity codes for VIP customers.
Collision-safe: retries up to 5 times on collision.
FCA: COBS 4 (financial promotions), BCOBS 2.2 (communications).
"""

from __future__ import annotations

from datetime import UTC, datetime
import secrets
import string
import uuid

from services.referral.models import (
    InMemoryReferralCodeStore,
    ReferralCode,
    ReferralCodeStorePort,
)

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 8
_MAX_RETRIES = 5


class CodeGenerator:
    """Generates unique referral codes — collision-safe with retry logic."""

    def __init__(self, code_store: ReferralCodeStorePort | None = None) -> None:
        self._store = code_store or InMemoryReferralCodeStore()

    def _generate_random_code(self) -> str:
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))

    def generate_code(
        self,
        customer_id: str,
        campaign_id: str,
        vanity_suffix: str = "",
    ) -> ReferralCode:
        """Generate a unique referral code.

        If vanity_suffix provided: code = "BANXE" + suffix[:4].upper()
        Otherwise: 8-char random alphanumeric.
        Retries up to 5 times on collision.

        Raises:
            ValueError: if code generation fails after max retries
        """
        for attempt in range(_MAX_RETRIES):
            if vanity_suffix:
                suffix = vanity_suffix.upper()[:4]
                candidate = f"BANXE{suffix}"[:_CODE_LENGTH].ljust(_CODE_LENGTH, "X")
            else:
                candidate = self._generate_random_code()

            existing = self._store.get_by_code(candidate)
            if existing is None:
                code = ReferralCode(
                    code_id=str(uuid.uuid4()),
                    customer_id=customer_id,
                    code=candidate,
                    campaign_id=campaign_id,
                    created_at=datetime.now(UTC),
                    is_vanity=bool(vanity_suffix),
                )
                self._store.save(code)
                return code

            # Vanity collision: append attempt suffix
            if vanity_suffix:
                vanity_suffix = f"{vanity_suffix[:3]}{attempt}"

        raise ValueError(f"Failed to generate unique code after {_MAX_RETRIES} attempts")

    def validate_code(self, code_str: str) -> dict:
        """Validate a referral code — check existence and usage limits.

        Returns {"valid": bool, "code": str, "campaign_id": str, "uses_remaining": int}.
        """
        ref_code = self._store.get_by_code(code_str)
        if ref_code is None:
            return {
                "valid": False,
                "code": code_str,
                "campaign_id": "",
                "uses_remaining": 0,
            }
        uses_remaining = ref_code.max_uses - ref_code.used_count
        return {
            "valid": uses_remaining > 0,
            "code": code_str,
            "campaign_id": ref_code.campaign_id,
            "uses_remaining": uses_remaining,
        }
