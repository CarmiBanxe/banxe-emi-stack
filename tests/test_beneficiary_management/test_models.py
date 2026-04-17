"""
tests/test_beneficiary_management/test_models.py — models + stores
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.beneficiary_management.models import (
    BLOCKED_JURISDICTIONS,
    FATF_GREYLIST,
    Beneficiary,
    BeneficiaryStatus,
    BeneficiaryType,
    CoPResult,
    InMemoryBeneficiaryStore,
    InMemoryCoPStore,
    InMemoryScreeningStore,
    InMemoryTrustedBeneficiaryStore,
    PaymentRail,
    ScreeningRecord,
    ScreeningResult,
    TrustedBeneficiary,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestBlockedJurisdictions:
    def test_contains_all_nine(self) -> None:
        for cc in ("RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"):
            assert cc in BLOCKED_JURISDICTIONS

    def test_is_frozenset(self) -> None:
        assert isinstance(BLOCKED_JURISDICTIONS, frozenset)


class TestFatfGreylist:
    def test_contains_pk_tr(self) -> None:
        assert "PK" in FATF_GREYLIST
        assert "TR" in FATF_GREYLIST

    def test_is_frozenset(self) -> None:
        assert isinstance(FATF_GREYLIST, frozenset)

    def test_does_not_overlap_with_blocked(self) -> None:
        assert BLOCKED_JURISDICTIONS.isdisjoint(FATF_GREYLIST)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestBeneficiaryType:
    def test_three_types(self) -> None:
        values = {e.value for e in BeneficiaryType}
        assert values == {"INDIVIDUAL", "BUSINESS", "JOINT"}


class TestBeneficiaryStatus:
    def test_four_statuses(self) -> None:
        values = {e.value for e in BeneficiaryStatus}
        assert values == {"PENDING", "ACTIVE", "SUSPENDED", "DEACTIVATED"}


class TestScreeningResult:
    def test_three_results(self) -> None:
        values = {e.value for e in ScreeningResult}
        assert values == {"NO_MATCH", "PARTIAL_MATCH", "MATCH"}


class TestPaymentRail:
    def test_five_rails(self) -> None:
        values = {e.value for e in PaymentRail}
        assert values == {"FPS", "BACS", "CHAPS", "SEPA", "SWIFT"}


# ---------------------------------------------------------------------------
# Beneficiary frozen dataclass
# ---------------------------------------------------------------------------


class TestBeneficiaryDataclass:
    def _make(self, **kwargs) -> Beneficiary:
        defaults = dict(
            beneficiary_id="b-001",
            customer_id="c-001",
            beneficiary_type=BeneficiaryType.INDIVIDUAL,
            name="John Smith",
            account_number="12345678",
            sort_code="40-00-01",
            iban="",
            bic="",
            currency="GBP",
            country_code="GB",
            status=BeneficiaryStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        defaults.update(kwargs)
        return Beneficiary(**defaults)

    def test_frozen(self) -> None:
        b = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            b.status = BeneficiaryStatus.ACTIVE  # type: ignore[misc]

    def test_replace_works(self) -> None:
        b = self._make()
        b2 = dataclasses.replace(b, status=BeneficiaryStatus.ACTIVE)
        assert b2.status == BeneficiaryStatus.ACTIVE
        assert b.status == BeneficiaryStatus.PENDING

    def test_defaults(self) -> None:
        b = self._make()
        assert b.trusted is False
        assert b.screening_result is None
        assert b.screening_at is None


# ---------------------------------------------------------------------------
# ScreeningRecord frozen dataclass
# ---------------------------------------------------------------------------


class TestScreeningRecordDataclass:
    def test_frozen(self) -> None:
        sr = ScreeningRecord(
            record_id="sr-001",
            beneficiary_id="b-001",
            result=ScreeningResult.NO_MATCH,
            checked_at=datetime.now(UTC),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            sr.record_id = "new"  # type: ignore[misc]

    def test_defaults(self) -> None:
        sr = ScreeningRecord(
            record_id="sr-001",
            beneficiary_id="b-001",
            result=ScreeningResult.NO_MATCH,
            checked_at=datetime.now(UTC),
        )
        assert sr.watchman_ref == ""
        assert sr.details == ""


# ---------------------------------------------------------------------------
# TrustedBeneficiary frozen dataclass
# ---------------------------------------------------------------------------


class TestTrustedBeneficiaryDataclass:
    def test_frozen(self) -> None:
        tb = TrustedBeneficiary(
            trust_id="t-001",
            beneficiary_id="b-001",
            customer_id="c-001",
            daily_limit=Decimal("1000.00"),
            approved_by="admin",
            approved_at=datetime.now(UTC),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            tb.daily_limit = Decimal("2000.00")  # type: ignore[misc]

    def test_default_is_active(self) -> None:
        tb = TrustedBeneficiary(
            trust_id="t-001",
            beneficiary_id="b-001",
            customer_id="c-001",
            daily_limit=Decimal("500.00"),
            approved_by="admin",
            approved_at=datetime.now(UTC),
        )
        assert tb.is_active is True


# ---------------------------------------------------------------------------
# InMemoryBeneficiaryStore
# ---------------------------------------------------------------------------


class TestInMemoryBeneficiaryStore:
    def _make_bene(self, bene_id: str = "b-001") -> Beneficiary:
        return Beneficiary(
            beneficiary_id=bene_id,
            customer_id="c-001",
            beneficiary_type=BeneficiaryType.INDIVIDUAL,
            name="Test User",
            account_number="",
            sort_code="",
            iban="",
            bic="",
            currency="GBP",
            country_code="GB",
            status=BeneficiaryStatus.PENDING,
            created_at=datetime.now(UTC),
        )

    def test_save_and_get(self) -> None:
        store = InMemoryBeneficiaryStore()
        b = self._make_bene()
        store.save(b)
        assert store.get("b-001") is b

    def test_get_missing_returns_none(self) -> None:
        store = InMemoryBeneficiaryStore()
        assert store.get("nonexistent") is None

    def test_update(self) -> None:
        store = InMemoryBeneficiaryStore()
        b = self._make_bene()
        store.save(b)
        updated = dataclasses.replace(b, status=BeneficiaryStatus.ACTIVE)
        store.update(updated)
        assert store.get("b-001").status == BeneficiaryStatus.ACTIVE

    def test_list_by_customer(self) -> None:
        store = InMemoryBeneficiaryStore()
        store.save(self._make_bene("b-001"))
        store.save(self._make_bene("b-002"))
        result = store.list_by_customer("c-001")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# InMemoryScreeningStore (append-only I-24)
# ---------------------------------------------------------------------------


class TestInMemoryScreeningStore:
    def test_append_only_no_update_method(self) -> None:
        store = InMemoryScreeningStore()
        assert not hasattr(store, "update")

    def test_save_and_list(self) -> None:
        store = InMemoryScreeningStore()
        sr = ScreeningRecord(
            record_id="sr-001",
            beneficiary_id="b-001",
            result=ScreeningResult.NO_MATCH,
            checked_at=datetime.now(UTC),
        )
        store.save(sr)
        assert len(store.list_by_beneficiary("b-001")) == 1

    def test_multiple_saves_append(self) -> None:
        store = InMemoryScreeningStore()
        for i in range(3):
            store.save(
                ScreeningRecord(
                    record_id=f"sr-{i}",
                    beneficiary_id="b-001",
                    result=ScreeningResult.NO_MATCH,
                    checked_at=datetime.now(UTC),
                )
            )
        assert len(store.list_by_beneficiary("b-001")) == 3


# ---------------------------------------------------------------------------
# InMemoryCoPStore (append-only I-24)
# ---------------------------------------------------------------------------


class TestInMemoryCoPStore:
    def test_append_only_no_update_method(self) -> None:
        store = InMemoryCoPStore()
        assert not hasattr(store, "update")

    def test_save_and_list(self) -> None:
        store = InMemoryCoPStore()
        cop = CoPResult(
            result="MATCH",
            beneficiary_id="b-001",
            expected_name="John",
            matched_name="John",
            checked_at=datetime.now(UTC),
        )
        store.save(cop)
        assert len(store.list_by_beneficiary("b-001")) == 1


# ---------------------------------------------------------------------------
# InMemoryTrustedBeneficiaryStore
# ---------------------------------------------------------------------------


class TestInMemoryTrustedBeneficiaryStore:
    def _make_trust(self, bene_id: str = "b-001") -> TrustedBeneficiary:
        return TrustedBeneficiary(
            trust_id="t-001",
            beneficiary_id=bene_id,
            customer_id="c-001",
            daily_limit=Decimal("1000.00"),
            approved_by="admin",
            approved_at=datetime.now(UTC),
        )

    def test_save_and_get(self) -> None:
        store = InMemoryTrustedBeneficiaryStore()
        trust = self._make_trust()
        store.save(trust)
        assert store.get_by_beneficiary("b-001") is trust

    def test_get_missing_returns_none(self) -> None:
        store = InMemoryTrustedBeneficiaryStore()
        assert store.get_by_beneficiary("nonexistent") is None

    def test_update(self) -> None:
        store = InMemoryTrustedBeneficiaryStore()
        trust = self._make_trust()
        store.save(trust)
        updated = dataclasses.replace(trust, is_active=False)
        store.update(updated)
        assert store.get_by_beneficiary("b-001").is_active is False
