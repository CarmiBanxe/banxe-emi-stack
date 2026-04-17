"""
services/beneficiary_management/beneficiary_agent.py — L2/L4 orchestration facade
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

from services.beneficiary_management.beneficiary_registry import BeneficiaryRegistry
from services.beneficiary_management.confirmation_of_payee import ConfirmationOfPayee
from services.beneficiary_management.models import (
    BeneficiaryType,
    InMemoryBeneficiaryStore,
    InMemoryCoPStore,
    InMemoryScreeningStore,
    InMemoryTrustedBeneficiaryStore,
)
from services.beneficiary_management.payment_rail_router import PaymentRailRouter
from services.beneficiary_management.sanctions_screener import SanctionsScreener
from services.beneficiary_management.trusted_beneficiary import TrustedBeneficiaryManager


class BeneficiaryAgent:
    """L2/L4 orchestration — add+delete+trust = HITL, screen = auto (I-27)."""

    def __init__(self) -> None:
        self._bene_store = InMemoryBeneficiaryStore()
        self._screen_store = InMemoryScreeningStore()
        self._trust_store = InMemoryTrustedBeneficiaryStore()
        self._cop_store = InMemoryCoPStore()
        self._registry = BeneficiaryRegistry(store=self._bene_store)
        self._screener = SanctionsScreener(
            beneficiary_store=self._bene_store,
            screening_store=self._screen_store,
        )
        self._router = PaymentRailRouter()
        self._cop = ConfirmationOfPayee(
            beneficiary_store=self._bene_store,
            cop_store=self._cop_store,
        )
        self._trust_mgr = TrustedBeneficiaryManager(
            beneficiary_store=self._bene_store,
            trust_store=self._trust_store,
        )

    def add_beneficiary(
        self,
        customer_id: str,
        beneficiary_type: BeneficiaryType,
        name: str,
        account_number: str = "",
        sort_code: str = "",
        iban: str = "",
        bic: str = "",
        currency: str = "GBP",
        country_code: str = "GB",
    ) -> dict[str, str]:
        return self._registry.add_beneficiary(
            customer_id=customer_id,
            beneficiary_type=beneficiary_type,
            name=name,
            account_number=account_number,
            sort_code=sort_code,
            iban=iban,
            bic=bic,
            currency=currency,
            country_code=country_code,
        )

    def screen_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        return self._screener.screen(beneficiary_id)

    def delete_beneficiary(self, beneficiary_id: str) -> dict[str, str]:
        """Deletion always requires HITL approval (I-27)."""
        return self._registry.delete_beneficiary(beneficiary_id)

    def route_payment(
        self,
        beneficiary_id: str,
        amount: Decimal,
        currency: str,
    ) -> dict[str, object]:
        beneficiary = self._bene_store.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError(f"Beneficiary {beneficiary_id} not found")
        return self._router.route(amount, currency, beneficiary.country_code)

    def check_payee(self, beneficiary_id: str, expected_name: str) -> dict[str, str]:
        return self._cop.check(beneficiary_id, expected_name)

    def list_beneficiaries(self, customer_id: str) -> dict[str, object]:
        return self._registry.list_beneficiaries(customer_id)
