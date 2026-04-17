"""
tests/test_referral/test_code_generator.py — Unit tests for CodeGenerator
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.referral.code_generator import _CODE_ALPHABET, _CODE_LENGTH, CodeGenerator
from services.referral.models import InMemoryReferralCodeStore, ReferralCode


@pytest.fixture()
def generator() -> CodeGenerator:
    return CodeGenerator()


# ── generate_code — random ─────────────────────────────────────────────────


def test_generate_code_returns_referral_code(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-1", "camp-1")
    assert isinstance(code, ReferralCode)


def test_generate_code_has_correct_customer_id(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-2", "camp-1")
    assert code.customer_id == "cust-2"


def test_generate_code_has_correct_campaign_id(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-3", "camp-xyz")
    assert code.campaign_id == "camp-xyz"


def test_generate_code_length_is_8(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-4", "camp-1")
    assert len(code.code) == _CODE_LENGTH


def test_generate_code_random_not_vanity(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-5", "camp-1")
    assert code.is_vanity is False


def test_generate_code_uses_uppercase_alphanumeric(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-6", "camp-1")
    for char in code.code:
        assert char in _CODE_ALPHABET


def test_generate_code_has_code_id(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-7", "camp-1")
    assert code.code_id != ""


def test_generate_code_has_created_at(generator: CodeGenerator) -> None:
    code = generator.generate_code("cust-8", "camp-1")
    assert code.created_at is not None


def test_generate_code_saves_to_store() -> None:
    store = InMemoryReferralCodeStore()
    gen = CodeGenerator(code_store=store)
    code = gen.generate_code("cust-9", "camp-1")
    assert store.get_by_code(code.code) is not None


def test_generate_two_codes_are_unique(generator: CodeGenerator) -> None:
    code1 = generator.generate_code("cust-10", "camp-1")
    code2 = generator.generate_code("cust-11", "camp-1")
    assert code1.code != code2.code


# ── generate_code — vanity ─────────────────────────────────────────────────


def test_generate_vanity_code_starts_with_banxe(generator: CodeGenerator) -> None:
    code = generator.generate_code("vip-cust", "camp-1", vanity_suffix="JOHN")
    assert code.code.startswith("BANXE")


def test_generate_vanity_code_is_vanity_flag_true(generator: CodeGenerator) -> None:
    code = generator.generate_code("vip-cust-2", "camp-1", vanity_suffix="ALEX")
    assert code.is_vanity is True


def test_generate_vanity_code_length_is_8(generator: CodeGenerator) -> None:
    code = generator.generate_code("vip-cust-3", "camp-1", vanity_suffix="BOB")
    assert len(code.code) == 8


def test_generate_vanity_suffix_truncated_to_4(generator: CodeGenerator) -> None:
    code = generator.generate_code("vip-cust-4", "camp-1", vanity_suffix="TOOLONG")
    # BANXE + first 4 chars of suffix = 9 chars → truncated to 8
    assert len(code.code) == 8


# ── validate_code ──────────────────────────────────────────────────────────


def test_validate_code_existing_code_is_valid(generator: CodeGenerator) -> None:
    code = generator.generate_code("val-cust-1", "camp-1")
    result = generator.validate_code(code.code)
    assert result["valid"] is True


def test_validate_code_existing_has_campaign_id(generator: CodeGenerator) -> None:
    code = generator.generate_code("val-cust-2", "camp-x")
    result = generator.validate_code(code.code)
    assert result["campaign_id"] == "camp-x"


def test_validate_code_nonexistent_is_invalid(generator: CodeGenerator) -> None:
    result = generator.validate_code("NOTEXIST")
    assert result["valid"] is False


def test_validate_code_nonexistent_uses_remaining_zero(generator: CodeGenerator) -> None:
    result = generator.validate_code("NOTEXIST")
    assert result["uses_remaining"] == 0


def test_validate_code_returns_code_string(generator: CodeGenerator) -> None:
    result = generator.validate_code("ANYTHING")
    assert result["code"] == "ANYTHING"


def test_validate_code_exhausted_returns_invalid() -> None:
    store = InMemoryReferralCodeStore()
    from datetime import UTC, datetime

    exhausted_code = ReferralCode(
        code_id="code-id-1",
        customer_id="cust-exhaust",
        code="EXHAUSTED",
        campaign_id="camp-1",
        created_at=datetime.now(UTC),
        used_count=100,
        max_uses=100,
    )
    store.save(exhausted_code)
    gen = CodeGenerator(code_store=store)
    result = gen.validate_code("EXHAUSTED")
    assert result["valid"] is False
    assert result["uses_remaining"] == 0
