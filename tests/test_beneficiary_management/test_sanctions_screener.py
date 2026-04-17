"""
tests/test_beneficiary_management/test_sanctions_screener.py
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.beneficiary_management.beneficiary_registry import BeneficiaryRegistry
from services.beneficiary_management.models import (
    BeneficiaryType,
    InMemoryBeneficiaryStore,
    InMemoryScreeningStore,
    ScreeningResult,
)
from services.beneficiary_management.sanctions_screener import SanctionsScreener


def _setup(country_code: str = "GB", name: str = "John Smith"):
    store = InMemoryBeneficiaryStore()
    screen_store = InMemoryScreeningStore()
    registry = BeneficiaryRegistry(store=store)
    screener = SanctionsScreener(beneficiary_store=store, screening_store=screen_store)
    r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, name, country_code=country_code)
    return screener, screen_store, r["beneficiary_id"]


class TestScreenNoMatch:
    def test_clean_beneficiary_no_match(self) -> None:
        screener, _, bene_id = _setup()
        result = screener.screen(bene_id)
        assert result["result"] == ScreeningResult.NO_MATCH.value

    def test_result_has_record_id(self) -> None:
        screener, _, bene_id = _setup()
        result = screener.screen(bene_id)
        assert result["record_id"] != ""

    def test_beneficiary_id_in_result(self) -> None:
        screener, _, bene_id = _setup()
        result = screener.screen(bene_id)
        assert result["beneficiary_id"] == bene_id


class TestScreenMatch:
    def test_blocked_country_returns_match(self) -> None:
        # Add directly via store to bypass registry's blocked-jurisdiction check
        store = InMemoryBeneficiaryStore()
        screen_store = InMemoryScreeningStore()
        from datetime import UTC, datetime

        from services.beneficiary_management.models import Beneficiary, BeneficiaryStatus

        b = Beneficiary(
            beneficiary_id="b-ru",
            customer_id="c-1",
            beneficiary_type=BeneficiaryType.INDIVIDUAL,
            name="Russian Entity",
            account_number="",
            sort_code="",
            iban="",
            bic="",
            currency="RUB",
            country_code="RU",
            status=BeneficiaryStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        store.save(b)
        screener = SanctionsScreener(beneficiary_store=store, screening_store=screen_store)
        result = screener.screen("b-ru")
        assert result["result"] == ScreeningResult.MATCH.value

    def test_blocked_ir_returns_match(self) -> None:
        store = InMemoryBeneficiaryStore()
        screen_store = InMemoryScreeningStore()
        from datetime import UTC, datetime

        from services.beneficiary_management.models import Beneficiary, BeneficiaryStatus

        b = Beneficiary(
            beneficiary_id="b-ir",
            customer_id="c-1",
            beneficiary_type=BeneficiaryType.INDIVIDUAL,
            name="Iranian Entity",
            account_number="",
            sort_code="",
            iban="",
            bic="",
            currency="IRR",
            country_code="IR",
            status=BeneficiaryStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        store.save(b)
        screener = SanctionsScreener(beneficiary_store=store, screening_store=screen_store)
        result = screener.screen("b-ir")
        assert result["result"] == ScreeningResult.MATCH.value


class TestScreenPartialMatch:
    def test_high_risk_name_partial_match(self) -> None:
        screener, _, bene_id = _setup(name="test_sanctioned")
        result = screener.screen(bene_id)
        assert result["result"] == ScreeningResult.PARTIAL_MATCH.value

    def test_ofac_listed_partial_match(self) -> None:
        screener, _, bene_id = _setup(name="ofac_listed")
        result = screener.screen(bene_id)
        assert result["result"] == ScreeningResult.PARTIAL_MATCH.value


class TestScreenHistory:
    def test_screening_history_accumulates(self) -> None:
        screener, screen_store, bene_id = _setup()
        screener.screen(bene_id)
        screener.screen(bene_id)
        history = screener.get_screening_history(bene_id)
        assert history["count"] == 2

    def test_history_has_record_ids(self) -> None:
        screener, _, bene_id = _setup()
        screener.screen(bene_id)
        history = screener.get_screening_history(bene_id)
        assert "records" in history
        assert history["records"][0]["record_id"] != ""

    def test_unknown_beneficiary_raises(self) -> None:
        screener, _, _ = _setup()
        with pytest.raises(ValueError, match="not found"):
            screener.screen("nonexistent")
