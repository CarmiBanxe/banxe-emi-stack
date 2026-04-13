"""EMI Product Catalogue — GAP-014 B-emi.

Defines Banxe EMI product types, their FCA regulatory attributes, and
safeguarding obligations per the Electronic Money Regulations 2011 (EMR 2011).

Regulatory references:
  EMR 2011 Reg.4   — definition of electronic money
  EMR 2011 Reg.7   — safeguarding obligations for e-money holders
  CASS 7.13        — segregated account requirements for client funds
  PS22/9 §2        — Consumer Duty fair value assessment (FCA)
  FCA DISP 1.1     — complaints handling
  PSD2 Art.18      — payment account access rights

Product taxonomy:
  EMONEY_ACCOUNT   — standard GBP e-money wallet (Reg.4)
  PREPAID_CARD     — physical/virtual Mastercard linked to e-money balance
  VIRTUAL_IBAN     — dedicated virtual IBAN for receiving SEPA/FPS payments
  SAVINGS_POT      — ringfenced savings pot (still e-money, not bank deposit)

Usage:
    catalogue = ProductCatalogue.default()
    product = catalogue.get("emoney-account-v1")
    print(product.is_safeguarded)  # True
    print(product.allowed_rails)   # ["fps", "bacs", "chaps"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ── Enumerations ───────────────────────────────────────────────────────────────


class ProductType(str, Enum):
    EMONEY_ACCOUNT = "EMONEY_ACCOUNT"  # GBP e-money wallet (EMR 2011 Reg.4)
    PREPAID_CARD = "PREPAID_CARD"  # Mastercard-linked prepaid
    VIRTUAL_IBAN = "VIRTUAL_IBAN"  # Dedicated IBAN (SEPA/FPS receive)
    SAVINGS_POT = "SAVINGS_POT"  # Ringfenced savings pot


class ProductStatus(str, Enum):
    ACTIVE = "ACTIVE"  # Available for new customers
    SUNSET = "SUNSET"  # Existing customers only, no new applications
    WITHDRAWN = "WITHDRAWN"  # Fully withdrawn, no new or existing


class RegulatoryScheme(str, Enum):
    EMR_2011 = "EMR_2011"  # Electronic Money Regulations 2011
    PSD2 = "PSD2"  # Payment Services Directive 2 (UK onshored)
    CASS = "CASS"  # Client Assets Sourcebook (safeguarding)


# ── Core product data ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FairValueAssessment:
    """Consumer Duty PS22/9 fair value summary per product.

    Attributes:
        assessed_date:    ISO date of last CFO/board fair value sign-off.
        annual_fee_gbp:   Total annual cost to customer (typical usage).
        value_statement:  One-line rationale for fair value conclusion.
        next_review_date: Mandatory review date (max 12 months forward).
    """

    assessed_date: str  # ISO-8601 date string
    annual_fee_gbp: Decimal
    value_statement: str
    next_review_date: str  # ISO-8601 date string


@dataclass
class EMIProduct:
    """One FCA-regulated EMI product.

    Attributes:
        product_id:       Unique slug used in TransactionContext.product_id.
        product_type:     ProductType enum.
        display_name:     Human-readable name for UI / invoice.
        status:           ACTIVE / SUNSET / WITHDRAWN.
        is_safeguarded:   True if client funds must be segregated (always True
                          for e-money holders, EMR 2011 Reg.7).
        allowed_rails:    Payment rails available to this product.
        max_balance_gbp:  Regulatory / risk maximum balance (None = uncapped).
        min_balance_gbp:  Minimum balance required to keep account open.
        fx_enabled:       True if the product supports non-GBP transactions.
        allowed_currencies: ISO-4217 list. Empty = any (if fx_enabled).
        regulatory_schemes: Which regulatory frameworks govern this product.
        fee_schedule_id:  Default fee schedule ID (maps to FeeEngine schedule).
        fair_value:       PS22/9 fair value assessment (None if not yet assessed).
        description:      Internal compliance description.
        version:          Incremented on each material change (CFO sign-off).
    """

    product_id: str
    product_type: ProductType
    display_name: str
    status: ProductStatus = ProductStatus.ACTIVE
    is_safeguarded: bool = True  # EMR 2011 Reg.7
    allowed_rails: list[str] = field(default_factory=list)
    max_balance_gbp: Decimal | None = None
    min_balance_gbp: Decimal = Decimal("0.00")
    fx_enabled: bool = False
    allowed_currencies: list[str] = field(default_factory=list)
    regulatory_schemes: list[RegulatoryScheme] = field(default_factory=list)
    fee_schedule_id: str = ""
    fair_value: FairValueAssessment | None = None
    description: str = ""
    version: int = 1

    def is_available(self) -> bool:
        """True if the product can be issued to new customers."""
        return self.status == ProductStatus.ACTIVE

    def allows_rail(self, rail: str) -> bool:
        """True if rail is permitted for this product. Empty list = all allowed."""
        if not self.allowed_rails:
            return True
        return rail.lower() in [r.lower() for r in self.allowed_rails]

    def allows_currency(self, currency: str) -> bool:
        """True if currency is permitted. Empty list = all (if fx_enabled)."""
        if not self.fx_enabled and currency.upper() != "GBP":
            return False
        if not self.allowed_currencies:
            return True
        return currency.upper() in [c.upper() for c in self.allowed_currencies]

    def validate_balance(self, balance_gbp: Decimal) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if balance_gbp < self.min_balance_gbp:
            errors.append(f"Balance £{balance_gbp} below minimum £{self.min_balance_gbp}")
        if self.max_balance_gbp is not None and balance_gbp > self.max_balance_gbp:
            errors.append(f"Balance £{balance_gbp} exceeds maximum £{self.max_balance_gbp}")
        return errors


# ── Product catalogue ──────────────────────────────────────────────────────────


class ProductCatalogue:
    """Registry of all EMI products.

    The catalogue is the single source of truth for product definitions.
    Use ProductCatalogue.default() for the standard Banxe product set.

    Args:
        products: List of EMIProduct objects to register.
    """

    def __init__(self, products: list[EMIProduct] | None = None) -> None:
        self._products: dict[str, EMIProduct] = {}
        for p in products or []:
            self.register(p)

    def register(self, product: EMIProduct) -> None:
        """Add or update a product in the catalogue."""
        if product.product_id in self._products:
            logger.warning(
                "ProductCatalogue: overwriting product '%s' (was v%d, now v%d)",
                product.product_id,
                self._products[product.product_id].version,
                product.version,
            )
        self._products[product.product_id] = product

    def get(self, product_id: str) -> EMIProduct | None:
        """Return product by ID, or None if not found."""
        return self._products.get(product_id)

    def get_or_raise(self, product_id: str) -> EMIProduct:
        """Return product by ID, raise KeyError if not found."""
        product = self._products.get(product_id)
        if product is None:
            raise KeyError(f"Unknown product_id: '{product_id}'")
        return product

    def list_active(self) -> list[EMIProduct]:
        """Return all ACTIVE products."""
        return [p for p in self._products.values() if p.status == ProductStatus.ACTIVE]

    def list_all(self) -> list[EMIProduct]:
        """Return all products regardless of status."""
        return list(self._products.values())

    def by_type(self, product_type: ProductType) -> list[EMIProduct]:
        """Return all products of a given type."""
        return [p for p in self._products.values() if p.product_type == product_type]

    @classmethod
    def default(cls) -> ProductCatalogue:
        """Return the standard Banxe EMI product catalogue.

        All products comply with EMR 2011, CASS 7.13, and PS22/9.
        Fee schedules reference FeeEngine schedule IDs.
        """
        return cls(
            products=[
                # ── 1. Standard GBP E-money Account ──────────────────────────────
                EMIProduct(
                    product_id="emoney-account-v1",
                    product_type=ProductType.EMONEY_ACCOUNT,
                    display_name="Banxe E-money Account",
                    status=ProductStatus.ACTIVE,
                    is_safeguarded=True,
                    allowed_rails=["fps", "bacs", "chaps"],
                    max_balance_gbp=Decimal("85000.00"),  # FSCS equivalent threshold
                    min_balance_gbp=Decimal("0.00"),
                    fx_enabled=False,
                    allowed_currencies=["GBP"],
                    regulatory_schemes=[RegulatoryScheme.EMR_2011, RegulatoryScheme.CASS],
                    fee_schedule_id="fps-standard-v1",
                    fair_value=FairValueAssessment(
                        assessed_date="2026-04-01",
                        annual_fee_gbp=Decimal("0.00"),
                        value_statement="No monthly fee; per-transaction cost of £0.20 FPS "
                        "is competitive vs. high-street alternatives.",
                        next_review_date="2027-04-01",
                    ),
                    description=(
                        "Core GBP e-money wallet. Client funds safeguarded under "
                        "EMR 2011 Reg.7 in Barclays segregated account. "
                        "Fair value assessed 2026-04-01 (CFO/David Goldstein sign-off)."
                    ),
                    version=1,
                ),
                # ── 2. Prepaid Mastercard ─────────────────────────────────────────
                EMIProduct(
                    product_id="prepaid-card-v1",
                    product_type=ProductType.PREPAID_CARD,
                    display_name="Banxe Prepaid Mastercard",
                    status=ProductStatus.ACTIVE,
                    is_safeguarded=True,
                    allowed_rails=["card"],
                    max_balance_gbp=Decimal("10000.00"),
                    min_balance_gbp=Decimal("0.00"),
                    fx_enabled=True,
                    allowed_currencies=[],  # Any Mastercard-settled currency
                    regulatory_schemes=[
                        RegulatoryScheme.EMR_2011,
                        RegulatoryScheme.PSD2,
                        RegulatoryScheme.CASS,
                    ],
                    fee_schedule_id="card-standard-v1",
                    fair_value=FairValueAssessment(
                        assessed_date="2026-04-01",
                        annual_fee_gbp=Decimal("9.99"),
                        value_statement="£9.99/year includes 3 free ATM withdrawals/month; "
                        "FX rate at Mastercard interbank — fair vs. market.",
                        next_review_date="2027-04-01",
                    ),
                    description=(
                        "Physical/virtual Mastercard. Balance held as e-money, safeguarded "
                        "per EMR 2011. FX via Mastercard settlement rate. "
                        "Paymentology card scheme processor (GAP-015 dependency)."
                    ),
                    version=1,
                ),
                # ── 3. Virtual IBAN ───────────────────────────────────────────────
                EMIProduct(
                    product_id="virtual-iban-v1",
                    product_type=ProductType.VIRTUAL_IBAN,
                    display_name="Banxe Virtual IBAN",
                    status=ProductStatus.ACTIVE,
                    is_safeguarded=True,
                    allowed_rails=["sepa", "fps", "chaps"],
                    max_balance_gbp=Decimal("250000.00"),
                    min_balance_gbp=Decimal("0.00"),
                    fx_enabled=True,
                    allowed_currencies=["GBP", "EUR", "USD"],
                    regulatory_schemes=[
                        RegulatoryScheme.EMR_2011,
                        RegulatoryScheme.PSD2,
                        RegulatoryScheme.CASS,
                    ],
                    fee_schedule_id="virtual-iban-v1",
                    fair_value=FairValueAssessment(
                        assessed_date="2026-04-01",
                        annual_fee_gbp=Decimal("120.00"),
                        value_statement="£10/month for dedicated IBAN with multi-currency "
                        "receipt; standard for SME treasury solutions.",
                        next_review_date="2027-04-01",
                    ),
                    description=(
                        "Dedicated virtual IBAN for SME payment collection. "
                        "Supports EUR SEPA Credit Transfer and GBP FPS inbound. "
                        "Segregated safeguarding per CASS 7.13."
                    ),
                    version=1,
                ),
                # ── 4. Savings Pot ────────────────────────────────────────────────
                EMIProduct(
                    product_id="savings-pot-v1",
                    product_type=ProductType.SAVINGS_POT,
                    display_name="Banxe Savings Pot",
                    status=ProductStatus.ACTIVE,
                    is_safeguarded=True,
                    allowed_rails=["fps"],  # Internal transfers only (via FPS)
                    max_balance_gbp=Decimal("85000.00"),
                    min_balance_gbp=Decimal("1.00"),
                    fx_enabled=False,
                    allowed_currencies=["GBP"],
                    regulatory_schemes=[RegulatoryScheme.EMR_2011, RegulatoryScheme.CASS],
                    fee_schedule_id="zero-fee",  # No fees on savings pot
                    fair_value=FairValueAssessment(
                        assessed_date="2026-04-01",
                        annual_fee_gbp=Decimal("0.00"),
                        value_statement="Zero-fee savings pot with ring-fenced e-money; "
                        "note: NOT a bank deposit, no FSCS protection.",
                        next_review_date="2027-04-01",
                    ),
                    description=(
                        "Ringfenced GBP savings pot backed by e-money. "
                        "NOT a bank deposit — customers informed per PS22/9 disclosure. "
                        "Safeguarded under EMR 2011 Reg.7."
                    ),
                    version=1,
                ),
            ]
        )
