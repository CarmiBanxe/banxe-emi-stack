"""Tests for src/products/emi_products.py — GAP-014 B-emi.

Coverage targets: ProductType, ProductStatus, EMIProduct lifecycle methods,
ProductCatalogue CRUD, default catalogue, FairValueAssessment.
"""

from decimal import Decimal

import pytest
from src.products import (
    EMIProduct,
    ProductCatalogue,
    ProductStatus,
    ProductType,
    RegulatoryScheme,
)

# ── EMIProduct.is_available ────────────────────────────────────────────────────


class TestEMIProductAvailability:
    def test_active_product_available(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", status=ProductStatus.ACTIVE)
        assert p.is_available() is True

    def test_sunset_product_not_available(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", status=ProductStatus.SUNSET)
        assert p.is_available() is False

    def test_withdrawn_product_not_available(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", status=ProductStatus.WITHDRAWN)
        assert p.is_available() is False


# ── EMIProduct.allows_rail ─────────────────────────────────────────────────────


class TestEMIProductAllowsRail:
    def test_empty_rails_allows_all(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", allowed_rails=[])
        assert p.allows_rail("fps") is True
        assert p.allows_rail("sepa") is True

    def test_rail_match_case_insensitive(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", allowed_rails=["FPS"])
        assert p.allows_rail("fps") is True
        assert p.allows_rail("FPS") is True

    def test_rail_no_match(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", allowed_rails=["fps"])
        assert p.allows_rail("sepa") is False


# ── EMIProduct.allows_currency ─────────────────────────────────────────────────


class TestEMIProductAllowsCurrency:
    def test_fx_disabled_only_gbp(self):
        p = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Test", fx_enabled=False)
        assert p.allows_currency("GBP") is True
        assert p.allows_currency("EUR") is False

    def test_fx_enabled_empty_list_allows_all(self):
        p = EMIProduct(
            "test",
            ProductType.PREPAID_CARD,
            "Test",
            fx_enabled=True,
            allowed_currencies=[],
        )
        assert p.allows_currency("EUR") is True
        assert p.allows_currency("USD") is True
        assert p.allows_currency("JPY") is True

    def test_fx_enabled_with_list(self):
        p = EMIProduct(
            "test",
            ProductType.VIRTUAL_IBAN,
            "Test",
            fx_enabled=True,
            allowed_currencies=["GBP", "EUR"],
        )
        assert p.allows_currency("GBP") is True
        assert p.allows_currency("EUR") is True
        assert p.allows_currency("USD") is False

    def test_currency_match_case_insensitive(self):
        p = EMIProduct(
            "test",
            ProductType.EMONEY_ACCOUNT,
            "Test",
            fx_enabled=True,
            allowed_currencies=["GBP"],
        )
        assert p.allows_currency("gbp") is True
        assert p.allows_currency("GBP") is True


# ── EMIProduct.validate_balance ────────────────────────────────────────────────


class TestEMIProductValidateBalance:
    def test_valid_balance_no_errors(self):
        p = EMIProduct(
            "test",
            ProductType.EMONEY_ACCOUNT,
            "Test",
            min_balance_gbp=Decimal("0"),
            max_balance_gbp=Decimal("85000"),
        )
        assert p.validate_balance(Decimal("1000")) == []

    def test_below_minimum_error(self):
        p = EMIProduct(
            "test",
            ProductType.SAVINGS_POT,
            "Test",
            min_balance_gbp=Decimal("1.00"),
        )
        errors = p.validate_balance(Decimal("0.50"))
        assert len(errors) == 1
        assert "minimum" in errors[0].lower()

    def test_above_maximum_error(self):
        p = EMIProduct(
            "test",
            ProductType.EMONEY_ACCOUNT,
            "Test",
            max_balance_gbp=Decimal("85000"),
        )
        errors = p.validate_balance(Decimal("90000"))
        assert len(errors) == 1
        assert "maximum" in errors[0].lower()

    def test_no_maximum_no_cap_error(self):
        p = EMIProduct(
            "test",
            ProductType.EMONEY_ACCOUNT,
            "Test",
            max_balance_gbp=None,
        )
        assert p.validate_balance(Decimal("999999")) == []

    def test_exact_minimum_valid(self):
        p = EMIProduct(
            "test",
            ProductType.SAVINGS_POT,
            "Test",
            min_balance_gbp=Decimal("1.00"),
        )
        assert p.validate_balance(Decimal("1.00")) == []

    def test_exact_maximum_valid(self):
        p = EMIProduct(
            "test",
            ProductType.EMONEY_ACCOUNT,
            "Test",
            max_balance_gbp=Decimal("85000"),
        )
        assert p.validate_balance(Decimal("85000")) == []


# ── ProductCatalogue ───────────────────────────────────────────────────────────


class TestProductCatalogue:
    def test_register_and_get(self):
        p = EMIProduct("test-001", ProductType.EMONEY_ACCOUNT, "Test")
        cat = ProductCatalogue()
        cat.register(p)
        assert cat.get("test-001") is p

    def test_get_unknown_returns_none(self):
        cat = ProductCatalogue()
        assert cat.get("nonexistent") is None

    def test_get_or_raise_raises_on_unknown(self):
        cat = ProductCatalogue()
        with pytest.raises(KeyError, match="nonexistent"):
            cat.get_or_raise("nonexistent")

    def test_get_or_raise_returns_product(self):
        p = EMIProduct("test-001", ProductType.EMONEY_ACCOUNT, "Test")
        cat = ProductCatalogue([p])
        assert cat.get_or_raise("test-001") is p

    def test_list_active_filters_status(self):
        active = EMIProduct("a", ProductType.EMONEY_ACCOUNT, "A", status=ProductStatus.ACTIVE)
        sunset = EMIProduct("b", ProductType.EMONEY_ACCOUNT, "B", status=ProductStatus.SUNSET)
        cat = ProductCatalogue([active, sunset])
        result = cat.list_active()
        assert len(result) == 1
        assert result[0].product_id == "a"

    def test_list_all_returns_all(self):
        p1 = EMIProduct("a", ProductType.EMONEY_ACCOUNT, "A")
        p2 = EMIProduct("b", ProductType.PREPAID_CARD, "B", status=ProductStatus.WITHDRAWN)
        cat = ProductCatalogue([p1, p2])
        assert len(cat.list_all()) == 2

    def test_by_type_filter(self):
        emoney = EMIProduct("a", ProductType.EMONEY_ACCOUNT, "A")
        card = EMIProduct("b", ProductType.PREPAID_CARD, "B")
        cat = ProductCatalogue([emoney, card])
        result = cat.by_type(ProductType.EMONEY_ACCOUNT)
        assert len(result) == 1
        assert result[0].product_id == "a"

    def test_register_overwrites(self):
        p_v1 = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "Old", version=1)
        p_v2 = EMIProduct("test", ProductType.EMONEY_ACCOUNT, "New", version=2)
        cat = ProductCatalogue([p_v1])
        cat.register(p_v2)
        assert cat.get("test").display_name == "New"
        assert cat.get("test").version == 2


# ── Default catalogue ──────────────────────────────────────────────────────────


class TestDefaultCatalogue:
    def setup_method(self):
        self.cat = ProductCatalogue.default()

    def test_emoney_account_exists(self):
        p = self.cat.get("emoney-account-v1")
        assert p is not None
        assert p.product_type == ProductType.EMONEY_ACCOUNT

    def test_prepaid_card_exists(self):
        p = self.cat.get("prepaid-card-v1")
        assert p is not None
        assert p.product_type == ProductType.PREPAID_CARD

    def test_virtual_iban_exists(self):
        p = self.cat.get("virtual-iban-v1")
        assert p is not None
        assert p.product_type == ProductType.VIRTUAL_IBAN

    def test_savings_pot_exists(self):
        p = self.cat.get("savings-pot-v1")
        assert p is not None
        assert p.product_type == ProductType.SAVINGS_POT

    def test_all_products_safeguarded(self):
        for p in self.cat.list_all():
            assert p.is_safeguarded, f"{p.product_id} must be safeguarded"

    def test_all_active_by_default(self):
        for p in self.cat.list_all():
            assert p.status == ProductStatus.ACTIVE, f"{p.product_id} should be ACTIVE"

    def test_all_have_fair_value_assessment(self):
        for p in self.cat.list_all():
            assert p.fair_value is not None, f"{p.product_id} missing fair value assessment"

    def test_emr_2011_in_all_regulatory_schemes(self):
        for p in self.cat.list_all():
            assert RegulatoryScheme.EMR_2011 in p.regulatory_schemes, (
                f"{p.product_id} must include EMR_2011"
            )

    def test_cass_in_all_products(self):
        for p in self.cat.list_all():
            assert RegulatoryScheme.CASS in p.regulatory_schemes, (
                f"{p.product_id} must include CASS"
            )

    def test_emoney_account_allows_fps(self):
        p = self.cat.get("emoney-account-v1")
        assert p.allows_rail("fps") is True

    def test_emoney_account_no_fx(self):
        p = self.cat.get("emoney-account-v1")
        assert p.allows_currency("EUR") is False

    def test_prepaid_card_fx_enabled(self):
        p = self.cat.get("prepaid-card-v1")
        assert p.fx_enabled is True

    def test_savings_pot_zero_fee(self):
        p = self.cat.get("savings-pot-v1")
        assert p.fee_schedule_id == "zero-fee"

    def test_virtual_iban_eur_allowed(self):
        p = self.cat.get("virtual-iban-v1")
        assert p.allows_currency("EUR") is True

    def test_default_has_four_products(self):
        assert len(self.cat.list_all()) == 4
