"""
services/merchant_acquiring/merchant_onboarding.py
IL-MAG-01 | Phase 20

KYB-based merchant onboarding: risk assessment, MCC classification, compliance.
High-risk merchants require HITL approval (I-27, L4).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.merchant_acquiring.models import (
    MAAuditPort,
    Merchant,
    MerchantRiskTier,
    MerchantStatus,
    MerchantStorePort,
)

_PROHIBITED_MCCS = {"7995", "9754", "7801"}  # gambling, lottery, betting
_HIGH_RISK_MCCS = {"6011", "5912", "7011"}  # cash, pharmacy, hotels
_MEDIUM_DAILY_LIMIT_THRESHOLD = Decimal("100000")


class MerchantOnboarding:
    """KYB onboarding service for merchants."""

    def __init__(self, store: MerchantStorePort, audit: MAAuditPort) -> None:
        self._store = store
        self._audit = audit

    async def onboard(
        self,
        name: str,
        legal_name: str,
        mcc: str,
        country: str,
        website: str | None,
        daily_limit_str: str,
        monthly_limit_str: str,
        actor: str,
    ) -> Merchant:
        """Onboard a new merchant after KYB checks."""
        if mcc in _PROHIBITED_MCCS:
            raise ValueError(f"MCC {mcc!r} is prohibited and cannot be onboarded")

        daily_limit = Decimal(daily_limit_str)
        monthly_limit = Decimal(monthly_limit_str)

        if mcc in _HIGH_RISK_MCCS:
            risk_tier = MerchantRiskTier.HIGH
        elif daily_limit > _MEDIUM_DAILY_LIMIT_THRESHOLD:
            risk_tier = MerchantRiskTier.MEDIUM
        else:
            risk_tier = MerchantRiskTier.LOW

        merchant = Merchant(
            id=str(uuid.uuid4()),
            name=name,
            legal_name=legal_name,
            mcc=mcc,
            country=country,
            website=website,
            status=MerchantStatus.PENDING_KYB,
            risk_tier=risk_tier,
            onboarded_at=None,
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
        )
        await self._store.save(merchant)
        await self._audit.log(
            "merchant.onboarded",
            merchant.id,
            actor,
            {"name": name, "mcc": mcc, "risk_tier": risk_tier.value},
        )
        return merchant

    async def approve_kyb(self, merchant_id: str, actor: str) -> Merchant:
        """Approve KYB and activate the merchant."""
        merchant = await self._store.get(merchant_id)
        if merchant is None:
            raise ValueError(f"Merchant {merchant_id!r} not found")

        updated = replace(
            merchant,
            status=MerchantStatus.ACTIVE,
            onboarded_at=datetime.now(UTC),
        )
        await self._store.save(updated)
        await self._audit.log(
            "merchant.kyb_approved",
            merchant_id,
            actor,
            {"previous_status": merchant.status.value},
        )
        return updated

    async def suspend(self, merchant_id: str, reason: str, actor: str) -> Merchant:
        """Suspend a merchant account."""
        merchant = await self._store.get(merchant_id)
        if merchant is None:
            raise ValueError(f"Merchant {merchant_id!r} not found")

        updated = replace(merchant, status=MerchantStatus.SUSPENDED)
        await self._store.save(updated)
        await self._audit.log(
            "merchant.suspended",
            merchant_id,
            actor,
            {"reason": reason, "previous_status": merchant.status.value},
        )
        return updated

    async def terminate(self, merchant_id: str, reason: str, actor: str) -> Merchant:
        """Terminate a merchant account."""
        merchant = await self._store.get(merchant_id)
        if merchant is None:
            raise ValueError(f"Merchant {merchant_id!r} not found")

        updated = replace(merchant, status=MerchantStatus.TERMINATED)
        await self._store.save(updated)
        await self._audit.log(
            "merchant.terminated",
            merchant_id,
            actor,
            {"reason": reason, "previous_status": merchant.status.value},
        )
        return updated

    async def get_merchant(self, merchant_id: str) -> Merchant | None:
        """Retrieve a merchant by ID."""
        return await self._store.get(merchant_id)

    async def list_merchants(self) -> list[Merchant]:
        """List all merchants."""
        return await self._store.list_all()
