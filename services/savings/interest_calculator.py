"""
services/savings/interest_calculator.py — Daily accrual, AER, tax withholding (I-01)
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_DAYS_IN_YEAR = Decimal("365")
_TAX_RATE_BASIC = Decimal("0.20")
_INTEREST_PRECISION = Decimal("0.00000001")  # 8dp
_PENALTY_DAYS: dict[str, int] = {
    "FIXED_TERM_3M": 30,
    "FIXED_TERM_6M": 60,
    "FIXED_TERM_12M": 90,
}


class InterestCalculator:
    def calculate_daily_interest(self, balance: Decimal, gross_rate: Decimal) -> Decimal:
        """Daily interest = balance * gross_rate / 365, quantized to 8dp (I-01)."""
        if balance <= Decimal("0") or gross_rate <= Decimal("0"):
            return Decimal("0")
        return (balance * gross_rate / _DAYS_IN_YEAR).quantize(
            _INTEREST_PRECISION, rounding=ROUND_HALF_UP
        )

    def calculate_aer_from_gross(
        self, gross_rate: Decimal, compounds_per_year: int = 365
    ) -> Decimal:
        """AER = (1 + gross_rate/n)^n - 1."""
        n = Decimal(str(compounds_per_year))
        aer = (Decimal("1") + gross_rate / n) ** compounds_per_year - Decimal("1")
        return aer.quantize(_INTEREST_PRECISION, rounding=ROUND_HALF_UP)

    def calculate_maturity_amount(
        self, principal: Decimal, gross_rate: Decimal, days: int
    ) -> Decimal:
        """Total maturity = principal + simple interest over term_days."""
        interest = (principal * gross_rate * Decimal(str(days)) / _DAYS_IN_YEAR).quantize(
            _INTEREST_PRECISION, rounding=ROUND_HALF_UP
        )
        return principal + interest

    def apply_tax_withholding(
        self,
        gross_interest: Decimal,
        tax_rate: Decimal = _TAX_RATE_BASIC,
    ) -> dict[str, str]:
        """Returns gross/tax_withheld/net as strings (I-05)."""
        tax = (gross_interest * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net = gross_interest - tax
        return {
            "gross_interest": str(gross_interest),
            "tax_withheld": str(tax),
            "net_interest": str(net),
            "tax_rate": str(tax_rate),
        }

    def calculate_penalty_amount(
        self, balance: Decimal, gross_rate: Decimal, penalty_days: int
    ) -> Decimal:
        """Penalty = balance * gross_rate * penalty_days / 365 (I-01)."""
        if balance <= Decimal("0") or penalty_days == 0:
            return Decimal("0.00")
        return (balance * gross_rate * Decimal(str(penalty_days)) / _DAYS_IN_YEAR).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
