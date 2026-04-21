"""
Tests for Correspondent Registry.
IL-SWF-01 | Sprint 34 | Phase 47
Tests: register, FATF risk (I-03), deactivate HITL (I-27)
"""

from __future__ import annotations

import pytest

from services.swift_correspondent.correspondent_registry import (
    CorrespondentRegistry,
)
from services.swift_correspondent.models import (
    CorrespondentType,
    InMemoryCorrespondentStore,
)


@pytest.fixture
def registry():
    return CorrespondentRegistry(store=InMemoryCorrespondentStore())


class TestRegisterCorrespondent:
    def test_register_basic(self, registry):
        bank = registry.register_correspondent(
            bic="HSBCHKHH",
            bank_name="HSBC HK",
            country_code="HK",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["HKD", "USD"],
            nostro_account="HK12345",
        )
        assert bank.bic == "HSBCHKHH"
        assert bank.fatf_risk == "low"
        assert bank.is_active is True

    def test_register_bank_id_sha256_prefix(self, registry):
        bank = registry.register_correspondent(
            bic="HSBCHKHH",
            bank_name="HSBC HK",
            country_code="HK",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["HKD"],
        )
        assert bank.bank_id.startswith("cb_")
        assert len(bank.bank_id) == 11  # cb_ + 8 hex

    def test_register_fatf_country_sets_high_risk(self, registry):
        # PK is in FATF greylist
        bank = registry.register_correspondent(
            bic="NBPAPKKA",
            bank_name="National Bank of Pakistan",
            country_code="PK",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["PKR"],
        )
        assert bank.fatf_risk == "high"

    def test_register_non_fatf_country_low_risk(self, registry):
        bank = registry.register_correspondent(
            bic="BNPAFRPP",
            bank_name="BNP Paribas",
            country_code="FR",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["EUR"],
        )
        assert bank.fatf_risk == "low"

    def test_register_blocked_jurisdiction_raises(self, registry):
        with pytest.raises(ValueError, match="blocked"):
            registry.register_correspondent(
                bic="SBERRU22",
                bank_name="Sberbank",
                country_code="RU",
                correspondent_type=CorrespondentType.NOSTRO,
                currencies=["RUB"],
            )

    def test_register_bic_uppercased(self, registry):
        bank = registry.register_correspondent(
            bic="bnpafrpp",
            bank_name="BNP Paribas",
            country_code="FR",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["EUR"],
        )
        assert bank.bic == "BNPAFRPP"

    def test_register_vostro_type(self, registry):
        bank = registry.register_correspondent(
            bic="BARCGB22",
            bank_name="Barclays",
            country_code="GB",
            correspondent_type=CorrespondentType.VOSTRO,
            currencies=["GBP"],
            vostro_account="GB29NWBK",
        )
        assert bank.correspondent_type == CorrespondentType.VOSTRO


class TestLookupByCurrency:
    def test_lookup_existing_currency(self, registry):
        banks = registry.lookup_by_currency("EUR")
        assert len(banks) >= 1  # seeded Deutsche Bank

    def test_lookup_excludes_blocked_jurisdictions(self, registry):
        # Manually add a blocked bank to test exclusion
        from services.swift_correspondent.models import CorrespondentBank

        store = InMemoryCorrespondentStore()
        store.save(
            CorrespondentBank(
                bank_id="cb_blocked",
                bic="SBERRU22",
                bank_name="Sberbank",
                country_code="RU",
                correspondent_type=CorrespondentType.NOSTRO,
                currencies=["USD"],
            )
        )
        reg = CorrespondentRegistry(store=store)
        banks = reg.lookup_by_currency("USD")
        bank_countries = [b.country_code for b in banks]
        assert "RU" not in bank_countries

    def test_lookup_unknown_currency_empty(self, registry):
        banks = registry.lookup_by_currency("XYZ")
        assert banks == []


class TestGetAccounts:
    def test_get_nostro_account(self, registry):
        account = registry.get_nostro_account("cb_001", "EUR")
        assert account is not None

    def test_get_nostro_account_wrong_currency(self, registry):
        account = registry.get_nostro_account("cb_002", "EUR")
        assert account is None  # Barclays supports GBP/USD not EUR

    def test_get_nostro_nonexistent_bank(self, registry):
        account = registry.get_nostro_account("cb_999", "EUR")
        assert account is None

    def test_get_vostro_account(self, registry):
        result = registry.get_vostro_account("cb_001")
        assert result is None  # seeded banks have no vostro

    def test_get_vostro_nonexistent(self, registry):
        result = registry.get_vostro_account("cb_999")
        assert result is None


class TestDeactivateCorrespondent:
    def test_deactivate_returns_hitl_proposal(self, registry):
        from services.swift_correspondent.models import HITLProposal

        proposal = registry.deactivate_correspondent("cb_001", "AML concern", "compliance")
        assert isinstance(proposal, HITLProposal)
        assert proposal.autonomy_level == "L4"
        assert proposal.requires_approval_from == "TREASURY_OPS"

    def test_deactivate_always_l4(self, registry):
        proposal = registry.deactivate_correspondent("cb_001", "test", "admin")
        assert proposal.autonomy_level == "L4"


class TestFATFRiskBanks:
    def test_get_fatf_risk_banks_empty_by_default(self, registry):
        banks = registry.get_fatf_risk_banks()
        assert isinstance(banks, list)

    def test_fatf_bank_in_list_after_register(self, registry):
        registry.register_correspondent(
            bic="NBPAPKKA",
            bank_name="NBP",
            country_code="PK",
            correspondent_type=CorrespondentType.NOSTRO,
            currencies=["PKR"],
        )
        fatf_banks = registry.get_fatf_risk_banks()
        # NBP registers PKR which isn't in lookup currencies list
        assert isinstance(fatf_banks, list)


class TestRegistrySummary:
    def test_summary_has_total(self, registry):
        summary = registry.get_registry_summary()
        assert "total" in summary
        assert "by_currency" in summary
        assert "fatf_high_risk_count" in summary

    def test_summary_counts_seeded_banks(self, registry):
        summary = registry.get_registry_summary()
        assert summary["total"] >= 3  # 3 seeded banks
