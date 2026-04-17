"""
tests/test_beneficiary_management/test_beneficiary_registry.py
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.beneficiary_management.beneficiary_registry import BeneficiaryRegistry
from services.beneficiary_management.models import (
    BeneficiaryStatus,
    BeneficiaryType,
    InMemoryBeneficiaryStore,
)


def _registry() -> tuple[BeneficiaryRegistry, InMemoryBeneficiaryStore]:
    store = InMemoryBeneficiaryStore()
    return BeneficiaryRegistry(store=store), store


class TestAddBeneficiary:
    def test_returns_beneficiary_id(self) -> None:
        registry, _ = _registry()
        result = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
        assert result["beneficiary_id"] != ""

    def test_status_pending(self) -> None:
        registry, _ = _registry()
        result = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
        assert result["status"] == BeneficiaryStatus.PENDING.value

    def test_name_in_result(self) -> None:
        registry, _ = _registry()
        result = registry.add_beneficiary("c-1", BeneficiaryType.BUSINESS, "Acme Ltd")
        assert result["name"] == "Acme Ltd"

    def test_customer_id_in_result(self) -> None:
        registry, _ = _registry()
        result = registry.add_beneficiary("c-99", BeneficiaryType.INDIVIDUAL, "Jane Doe")
        assert result["customer_id"] == "c-99"

    def test_blocked_jurisdiction_ru_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="blocked jurisdiction"):
            registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Test", country_code="RU")

    def test_blocked_jurisdiction_ir_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="blocked jurisdiction"):
            registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Test", country_code="IR")

    def test_blocked_jurisdiction_kp_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="blocked jurisdiction"):
            registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Test", country_code="KP")

    def test_blocked_jurisdiction_by_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="blocked jurisdiction"):
            registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Test", country_code="BY")

    def test_gb_is_allowed(self) -> None:
        registry, _ = _registry()
        result = registry.add_beneficiary(
            "c-1", BeneficiaryType.INDIVIDUAL, "UK Person", country_code="GB"
        )
        assert result["status"] == BeneficiaryStatus.PENDING.value


class TestVerifyBeneficiary:
    def test_status_becomes_active(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        result = registry.verify_beneficiary(r["beneficiary_id"])
        assert result["status"] == BeneficiaryStatus.ACTIVE.value

    def test_unknown_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="not found"):
            registry.verify_beneficiary("nonexistent")

    def test_already_active_raises(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        registry.verify_beneficiary(r["beneficiary_id"])
        with pytest.raises(ValueError, match="not PENDING"):
            registry.verify_beneficiary(r["beneficiary_id"])


class TestActivateDeactivate:
    def test_activate_sets_active(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        result = registry.activate_beneficiary(r["beneficiary_id"])
        assert result["status"] == BeneficiaryStatus.ACTIVE.value

    def test_deactivate_sets_deactivated(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        result = registry.deactivate_beneficiary(r["beneficiary_id"])
        assert result["status"] == BeneficiaryStatus.DEACTIVATED.value

    def test_activate_unknown_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="not found"):
            registry.activate_beneficiary("nonexistent")

    def test_deactivate_unknown_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="not found"):
            registry.deactivate_beneficiary("nonexistent")


class TestDeleteBeneficiary:
    def test_always_hitl_required(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        result = registry.delete_beneficiary(r["beneficiary_id"])
        assert result["status"] == "HITL_REQUIRED"

    def test_reason_in_result(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        result = registry.delete_beneficiary(r["beneficiary_id"])
        assert "reason" in result

    def test_unknown_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="not found"):
            registry.delete_beneficiary("nonexistent")


class TestGetAndListBeneficiaries:
    def test_get_returns_name(self) -> None:
        registry, _ = _registry()
        r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Alice")
        detail = registry.get_beneficiary(r["beneficiary_id"])
        assert detail["name"] == "Alice"

    def test_get_unknown_raises(self) -> None:
        registry, _ = _registry()
        with pytest.raises(ValueError, match="not found"):
            registry.get_beneficiary("nonexistent")

    def test_list_empty(self) -> None:
        registry, _ = _registry()
        result = registry.list_beneficiaries("c-unknown")
        assert result["count"] == 0

    def test_list_count_matches(self) -> None:
        registry, _ = _registry()
        registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Alice")
        registry.add_beneficiary("c-1", BeneficiaryType.BUSINESS, "Acme Ltd")
        result = registry.list_beneficiaries("c-1")
        assert result["count"] == 2
