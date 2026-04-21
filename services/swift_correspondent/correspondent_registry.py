"""
services/swift_correspondent/correspondent_registry.py
Correspondent Bank Registry
IL-SWF-01 | Sprint 34 | Phase 47

FCA: MLR 2017 Reg.28 (correspondent due diligence)
Trust Zone: RED

FATF greylist check on all registrations (I-03).
Deactivation always HITL (I-27).
"""

from __future__ import annotations

import hashlib
import logging

from services.swift_correspondent.models import (
    CorrespondentBank,
    CorrespondentStore,
    CorrespondentType,
    HITLProposal,
    InMemoryCorrespondentStore,
)

logger = logging.getLogger(__name__)

FATF_GREYLIST: set[str] = {
    "PK",
    "AE",
    "JO",
    "TN",
    "VN",
    "LK",
    "NG",
    "ET",
    "KH",
    "SN",
    "MN",
    "YE",
}
BLOCKED_JURISDICTIONS: set[str] = {
    "RU",
    "BY",
    "IR",
    "KP",
    "CU",
    "MM",
    "AF",
    "VE",
    "SY",
}


class CorrespondentRegistry:
    """Registry for correspondent bank relationships.

    MLR 2017 Reg.28 due diligence: FATF risk assessment on registration.
    Blocked jurisdictions excluded from lookups (I-03).
    Deactivation is always HITL L4 (I-27).
    """

    def __init__(self, store: CorrespondentStore | None = None) -> None:
        """Initialise registry with optional correspondent store."""
        self._store: CorrespondentStore = store or InMemoryCorrespondentStore()

    def register_correspondent(
        self,
        bic: str,
        bank_name: str,
        country_code: str,
        correspondent_type: CorrespondentType,
        currencies: list[str],
        nostro_account: str | None = None,
        vostro_account: str | None = None,
    ) -> CorrespondentBank:
        """Register a new correspondent bank.

        I-03: FATF greylist check — sets fatf_risk="high" if country listed.
        bank_id = sha256(bic)[:8].

        Args:
            bic: Bank Identifier Code (8 or 11 chars).
            bank_name: Full bank name.
            country_code: ISO 3166-1 alpha-2 country code.
            correspondent_type: NOSTRO or VOSTRO relationship.
            currencies: List of supported ISO 4217 currency codes.
            nostro_account: Our account IBAN at their bank.
            vostro_account: Their account IBAN at our bank.

        Returns:
            Registered CorrespondentBank instance.
        """
        bank_id = f"cb_{hashlib.sha256(bic.encode()).hexdigest()[:8]}"
        fatf_risk = "low"

        if country_code.upper() in BLOCKED_JURISDICTIONS:
            raise ValueError(f"Country {country_code} is a blocked jurisdiction (I-02)")

        if country_code.upper() in FATF_GREYLIST:
            fatf_risk = "high"
            logger.warning(
                "FATF greylist country detected: %s for bank %s (I-03)", country_code, bic
            )

        bank = CorrespondentBank(
            bank_id=bank_id,
            bic=bic.upper(),
            bank_name=bank_name,
            country_code=country_code.upper(),
            correspondent_type=correspondent_type,
            currencies=currencies,
            nostro_account=nostro_account,
            vostro_account=vostro_account,
            is_active=True,
            fatf_risk=fatf_risk,
        )
        self._store.save(bank)
        logger.info("Registered correspondent bank_id=%s bic=%s risk=%s", bank_id, bic, fatf_risk)
        return bank

    def lookup_by_currency(self, currency: str) -> list[CorrespondentBank]:
        """Find active correspondent banks supporting a currency.

        Excludes blocked jurisdictions (I-02).

        Args:
            currency: ISO 4217 currency code.

        Returns:
            List of active CorrespondentBank instances.
        """
        candidates = self._store.find_by_currency(currency)
        return [
            b
            for b in candidates
            if b.is_active and b.country_code.upper() not in BLOCKED_JURISDICTIONS
        ]

    def get_nostro_account(self, bank_id: str, currency: str) -> str | None:
        """Get nostro account for a bank/currency combination.

        Args:
            bank_id: Correspondent bank ID.
            currency: ISO 4217 currency code.

        Returns:
            Nostro account string or None.
        """
        bank = self._store.get(bank_id)
        if bank is None or currency not in bank.currencies:
            return None
        return bank.nostro_account

    def get_vostro_account(self, bank_id: str) -> str | None:
        """Get vostro account for a bank.

        Args:
            bank_id: Correspondent bank ID.

        Returns:
            Vostro account string or None.
        """
        bank = self._store.get(bank_id)
        return bank.vostro_account if bank else None

    def deactivate_correspondent(self, bank_id: str, reason: str, actor: str) -> HITLProposal:
        """Propose deactivation of a correspondent bank (always HITL, I-27).

        Deactivation affects payment routing — always requires L4 approval.

        Args:
            bank_id: Correspondent bank ID to deactivate.
            reason: Reason for deactivation.
            actor: Actor requesting deactivation.

        Returns:
            HITLProposal for L4 human approval.
        """
        logger.warning(
            "Deactivation proposed for bank_id=%s by actor=%s reason=%s",
            bank_id,
            actor,
            reason,
        )
        return HITLProposal(
            action="DEACTIVATE_CORRESPONDENT",
            message_id=bank_id,
            requires_approval_from="TREASURY_OPS",
            reason=f"Deactivation requested by {actor}: {reason}",
            autonomy_level="L4",
        )

    def get_fatf_risk_banks(self) -> list[CorrespondentBank]:
        """Get all correspondent banks with high FATF risk (I-03).

        Returns:
            List of CorrespondentBank with fatf_risk='high'.
        """
        all_banks: list[CorrespondentBank] = []
        seen: set[str] = set()
        for currency in ["GBP", "EUR", "USD", "JPY", "CHF"]:
            for bank in self._store.find_by_currency(currency):
                if bank.bank_id not in seen:
                    all_banks.append(bank)
                    seen.add(bank.bank_id)
        return [b for b in all_banks if b.fatf_risk == "high"]

    def get_registry_summary(self) -> dict[str, object]:
        """Get summary statistics of the correspondent registry.

        Returns:
            Dict with total, by_currency, fatf_high_risk_count.
        """
        currency_map: dict[str, int] = {}
        all_banks: list[CorrespondentBank] = []
        seen: set[str] = set()
        for currency in ["GBP", "EUR", "USD", "JPY", "CHF", "AED", "SGD"]:
            banks = self._store.find_by_currency(currency)
            if banks:
                currency_map[currency] = len(banks)
            for bank in banks:
                if bank.bank_id not in seen:
                    all_banks.append(bank)
                    seen.add(bank.bank_id)

        fatf_high = sum(1 for b in all_banks if b.fatf_risk == "high")
        return {
            "total": len(all_banks),
            "by_currency": currency_map,
            "fatf_high_risk_count": fatf_high,
        }
