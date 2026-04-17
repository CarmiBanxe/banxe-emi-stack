"""
tests/test_beneficiary_management/test_trusted_beneficiary.py
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.beneficiary_management.beneficiary_registry import BeneficiaryRegistry
from services.beneficiary_management.models import (
    BeneficiaryType,
    InMemoryBeneficiaryStore,
    InMemoryTrustedBeneficiaryStore,
)
from services.beneficiary_management.trusted_beneficiary import TrustedBeneficiaryManager


def _setup():
    store = InMemoryBeneficiaryStore()
    trust_store = InMemoryTrustedBeneficiaryStore()
    registry = BeneficiaryRegistry(store=store)
    manager = TrustedBeneficiaryManager(beneficiary_store=store, trust_store=trust_store)
    r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
    bene_id = r["beneficiary_id"]
    return manager, bene_id


class TestMarkTrusted:
    def test_always_hitl_required(self) -> None:
        manager, bene_id = _setup()
        result = manager.mark_trusted(bene_id, "c-1", Decimal("1000.00"))
        assert result["status"] == "HITL_REQUIRED"

    def test_beneficiary_id_in_result(self) -> None:
        manager, bene_id = _setup()
        result = manager.mark_trusted(bene_id, "c-1", Decimal("1000.00"))
        assert result["beneficiary_id"] == bene_id

    def test_daily_limit_in_result(self) -> None:
        manager, bene_id = _setup()
        result = manager.mark_trusted(bene_id, "c-1", Decimal("500.00"))
        assert result["daily_limit"] == "500.00"

    def test_zero_limit_raises(self) -> None:
        manager, bene_id = _setup()
        with pytest.raises(ValueError, match="positive"):
            manager.mark_trusted(bene_id, "c-1", Decimal("0"))

    def test_negative_limit_raises(self) -> None:
        manager, bene_id = _setup()
        with pytest.raises(ValueError, match="positive"):
            manager.mark_trusted(bene_id, "c-1", Decimal("-100.00"))

    def test_unknown_beneficiary_raises(self) -> None:
        manager, _ = _setup()
        with pytest.raises(ValueError, match="not found"):
            manager.mark_trusted("nonexistent", "c-1", Decimal("1000.00"))


class TestConfirmTrust:
    def test_status_trusted(self) -> None:
        manager, bene_id = _setup()
        result = manager.confirm_trust(bene_id, "c-1", Decimal("1000.00"), "admin-001")
        assert result["status"] == "TRUSTED"

    def test_trust_id_returned(self) -> None:
        manager, bene_id = _setup()
        result = manager.confirm_trust(bene_id, "c-1", Decimal("1000.00"), "admin-001")
        assert result["trust_id"] != ""

    def test_daily_limit_as_string(self) -> None:
        manager, bene_id = _setup()
        result = manager.confirm_trust(bene_id, "c-1", Decimal("750.50"), "admin-001")
        assert result["daily_limit"] == "750.50"

    def test_unknown_beneficiary_raises(self) -> None:
        manager, _ = _setup()
        with pytest.raises(ValueError, match="not found"):
            manager.confirm_trust("nonexistent", "c-1", Decimal("1000.00"), "admin")


class TestRevokeTrust:
    def test_status_trust_revoked(self) -> None:
        manager, bene_id = _setup()
        manager.confirm_trust(bene_id, "c-1", Decimal("1000.00"), "admin")
        result = manager.revoke_trust(bene_id)
        assert result["status"] == "TRUST_REVOKED"

    def test_no_trust_record_raises(self) -> None:
        manager, bene_id = _setup()
        with pytest.raises(ValueError, match="No trust record"):
            manager.revoke_trust(bene_id)


class TestIsTrusted:
    def test_not_trusted_initially(self) -> None:
        manager, bene_id = _setup()
        assert manager.is_trusted(bene_id) is False

    def test_trusted_after_confirm(self) -> None:
        manager, bene_id = _setup()
        manager.confirm_trust(bene_id, "c-1", Decimal("1000.00"), "admin")
        assert manager.is_trusted(bene_id) is True

    def test_not_trusted_after_revoke(self) -> None:
        manager, bene_id = _setup()
        manager.confirm_trust(bene_id, "c-1", Decimal("1000.00"), "admin")
        manager.revoke_trust(bene_id)
        assert manager.is_trusted(bene_id) is False


class TestGetDailyLimit:
    def test_not_trusted_returns_no_limit(self) -> None:
        manager, bene_id = _setup()
        result = manager.get_daily_limit(bene_id)
        assert result["trusted"] is False
        assert result["daily_limit"] is None

    def test_trusted_returns_limit(self) -> None:
        manager, bene_id = _setup()
        manager.confirm_trust(bene_id, "c-1", Decimal("2000.00"), "admin")
        result = manager.get_daily_limit(bene_id)
        assert result["trusted"] is True
        assert result["daily_limit"] == "2000.00"

    def test_revoked_returns_no_limit(self) -> None:
        manager, bene_id = _setup()
        manager.confirm_trust(bene_id, "c-1", Decimal("1000.00"), "admin")
        manager.revoke_trust(bene_id)
        result = manager.get_daily_limit(bene_id)
        assert result["daily_limit"] is None
