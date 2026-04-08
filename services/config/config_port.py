"""
config_port.py — Config-as-Data: product fees, limits, enums
Geniusto v5 Pattern #6 — Config-as-Data (fees/limits/enums from store)
FCA: COBS 6 (fee disclosure), PSR 2017 (payment limits)

WHY THIS FILE EXISTS
--------------------
Geniusto v5 stores all fee schedules, product limits, and product-level
enumerations in a central config registry (originally PostgreSQL, can be YAML).
This eliminates hardcoded magic numbers scattered across services:
  - payment_service.py had hardcoded £1,000,000 FPS limit
  - mock_fraud_adapter.py had hardcoded £10,000 EDD threshold
  - No per-product fee differentiation was possible

ConfigPort (hexagonal port) lets:
  - YAMLConfigStore: load from config/banxe_config.yaml (default — no DB needed)
  - PostgreSQLConfigStore: load from DB (production — hot-reload without deploy)
  - InMemoryConfigStore: inject in tests

FCA obligations:
  - COBS 6.1A: fee schedule must be disclosed before account opening
  - PSR 2017 Reg.67: payment execution limits must be documented
  - MLR 2017 Reg.28: per-entity EDD thresholds (see aml_thresholds.py for AML)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol


# ── Fee schedule ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeeSchedule:
    """
    Single fee rule for one product + transaction type.

    Examples:
        FPS domestic: flat £0.20
        FX spot:      0.25% with £1.00 min, £500 max
        SEPA Instant: flat €1.00
    """
    product_id: str
    tx_type: str            # FPS | SEPA_CT | SEPA_INSTANT | BACS | FX | CARD_PAYMENT
    fee_type: str           # FLAT | PERCENTAGE | MIXED
    flat_fee: Decimal       # Fixed component (0 if PERCENTAGE only)
    percentage: Decimal     # e.g. Decimal("0.0025") = 0.25% (0 if FLAT only)
    min_fee: Decimal        # Minimum charged (applies after calculation)
    max_fee: Optional[Decimal]  # None = uncapped
    currency: str = "GBP"

    def calculate(self, amount: Decimal) -> Decimal:
        """Calculate fee for given transaction amount."""
        fee = self.flat_fee + (amount * self.percentage)
        fee = max(fee, self.min_fee)
        if self.max_fee is not None:
            fee = min(fee, self.max_fee)
        return fee.quantize(Decimal("0.01"))


# ── Payment limits ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PaymentLimits:
    """
    Payment limits per product + entity type.

    Individual limits are tighter (PSR 2017 consumer protections).
    Company limits reflect B2B payment volumes.
    """
    product_id: str
    entity_type: str        # INDIVIDUAL | COMPANY
    single_tx_max: Decimal  # Max per single transaction
    daily_max: Decimal      # Max total outbound per day
    monthly_max: Decimal    # Max total outbound per month
    daily_tx_count: int     # Max number of outbound transactions per day
    monthly_tx_count: int   # Max number of outbound transactions per month
    min_tx: Decimal = Decimal("0.01")

    def check_single(self, amount: Decimal) -> bool:
        """True if amount is within single-tx limit."""
        return self.min_tx <= amount <= self.single_tx_max

    def check_daily(self, amount: Decimal, daily_total: Decimal, daily_count: int) -> bool:
        """True if amount + daily_total stays within daily limits."""
        return (
            (daily_total + amount) <= self.daily_max
            and (daily_count + 1) <= self.daily_tx_count
        )

    def check_monthly(self, amount: Decimal, monthly_total: Decimal, monthly_count: int) -> bool:
        """True if amount + monthly_total stays within monthly limits."""
        return (
            (monthly_total + amount) <= self.monthly_max
            and (monthly_count + 1) <= self.monthly_tx_count
        )


# ── Product config ─────────────────────────────────────────────────────────────

@dataclass
class ProductConfig:
    """
    Full runtime configuration for one product (e.g. EMI_ACCOUNT).
    Contains fee schedules for every tx type + limits per entity type.
    """
    product_id: str
    display_name: str
    currencies: list[str]
    fee_schedules: list[FeeSchedule]
    individual_limits: PaymentLimits
    company_limits: PaymentLimits
    active: bool = True

    def get_fee(self, tx_type: str) -> Optional[FeeSchedule]:
        for fs in self.fee_schedules:
            if fs.tx_type == tx_type:
                return fs
        return None

    def get_limits(self, entity_type: str) -> Optional[PaymentLimits]:
        if entity_type == "INDIVIDUAL":
            return self.individual_limits
        if entity_type == "COMPANY":
            return self.company_limits
        return None


# ── Config port (hexagonal) ────────────────────────────────────────────────────

class ConfigPort(Protocol):
    """Hexagonal port for runtime business configuration."""

    def get_product(self, product_id: str) -> Optional[ProductConfig]: ...
    def list_products(self) -> list[ProductConfig]: ...
    def get_fee(self, product_id: str, tx_type: str) -> Optional[FeeSchedule]: ...
    def get_limits(self, product_id: str, entity_type: str) -> Optional[PaymentLimits]: ...
    def reload(self) -> None: ...
