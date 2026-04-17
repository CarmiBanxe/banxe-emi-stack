"""
tests/test_beneficiary_management/test_confirmation_of_payee.py
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.beneficiary_management.beneficiary_registry import BeneficiaryRegistry
from services.beneficiary_management.confirmation_of_payee import ConfirmationOfPayee
from services.beneficiary_management.models import (
    BeneficiaryType,
    InMemoryBeneficiaryStore,
    InMemoryCoPStore,
)


def _setup(name: str = "John Smith"):
    store = InMemoryBeneficiaryStore()
    cop_store = InMemoryCoPStore()
    registry = BeneficiaryRegistry(store=store)
    cop = ConfirmationOfPayee(beneficiary_store=store, cop_store=cop_store)
    r = registry.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, name)
    return cop, cop_store, r["beneficiary_id"]


class TestCoPMatch:
    def test_exact_match(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "John Smith")
        assert result["result"] == "MATCH"

    def test_case_insensitive_match(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "JOHN SMITH")
        assert result["result"] == "MATCH"

    def test_leading_trailing_spaces_match(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "  John Smith  ")
        assert result["result"] == "MATCH"


class TestCoPCloseMatch:
    def test_first_word_matches(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "John Jones")
        assert result["result"] == "CLOSE_MATCH"

    def test_first_word_case_insensitive(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "JOHN Doe")
        assert result["result"] == "CLOSE_MATCH"


class TestCoPNoMatch:
    def test_no_match(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "Alice Brown")
        assert result["result"] == "NO_MATCH"

    def test_partial_last_name_no_match(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "Jane Smith")
        assert result["result"] == "NO_MATCH"


class TestCoPResultFields:
    def test_expected_name_in_result(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "John Smith")
        assert result["expected_name"] == "John Smith"

    def test_matched_name_in_result(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "John Smith")
        assert result["matched_name"] == "John Smith"

    def test_beneficiary_id_in_result(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        result = cop.check(bene_id, "John Smith")
        assert result["beneficiary_id"] == bene_id

    def test_unknown_beneficiary_raises(self) -> None:
        cop, _, _ = _setup()
        with pytest.raises(ValueError, match="not found"):
            cop.check("nonexistent", "John Smith")


class TestCoPHistory:
    def test_history_accumulates(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        cop.check(bene_id, "John Smith")
        cop.check(bene_id, "John Doe")
        history = cop.get_cop_history(bene_id)
        assert history["count"] == 2

    def test_history_has_results(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        cop.check(bene_id, "John Smith")
        history = cop.get_cop_history(bene_id)
        assert len(history["checks"]) == 1
        assert "result" in history["checks"][0]

    def test_empty_history(self) -> None:
        cop, _, bene_id = _setup("John Smith")
        history = cop.get_cop_history(bene_id)
        assert history["count"] == 0
