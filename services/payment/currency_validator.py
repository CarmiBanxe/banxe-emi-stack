"""
services/payment/currency_validator.py
Multi-currency validation for payment processing (IL-PAY-02).

I-01: All monetary comparisons use Decimal — never float.
I-02: Blocked jurisdictions checked before currency validation.
I-04: EDD thresholds enforced per currency.
"""

from __future__ import annotations

from decimal import Decimal

from services.payment.payment_models import SUPPORTED_CURRENCIES


class CurrencyValidationError(ValueError):
    """Raised when currency validation fails."""


class AmountValidationError(ValueError):
    """Raised when amount validation fails."""


# Scheme limits per currency (Decimal, I-01).
SCHEME_LIMITS: dict[str, Decimal] = {
    "GBP": Decimal("1000000"),  # FPS scheme limit £1M
    "EUR": Decimal("100000"),  # SEPA Instant €100k (SEPA CT unlimited)
    "USD": Decimal("10000000"),  # No hard scheme limit, internal cap $10M
}

# EDD thresholds per currency (I-04). Amounts >= trigger require HITL.
EDD_THRESHOLDS: dict[str, Decimal] = {
    "GBP": Decimal("10000"),
    "EUR": Decimal("10000"),
    "USD": Decimal("10000"),
}

# High-value thresholds requiring MLRO escalation (I-04).
HIGH_VALUE_THRESHOLDS: dict[str, Decimal] = {
    "GBP": Decimal("50000"),
    "EUR": Decimal("50000"),
    "USD": Decimal("50000"),
}


def validate_currency(currency: str) -> None:
    """Validate that the currency is supported (GBP, EUR, USD)."""
    if currency not in SUPPORTED_CURRENCIES:
        raise CurrencyValidationError(
            f"Unsupported currency: {currency}. "
            f"Supported: {', '.join(sorted(SUPPORTED_CURRENCIES))}"
        )


def validate_amount(amount: Decimal, currency: str) -> None:
    """Validate amount is Decimal, positive, and within scheme limits (I-01)."""
    if not isinstance(amount, Decimal):
        raise AmountValidationError(f"Amount must be Decimal, got {type(amount).__name__} (I-01)")
    if amount <= Decimal("0"):
        raise AmountValidationError(f"Amount must be positive, got {amount}")
    validate_currency(currency)
    limit = SCHEME_LIMITS.get(currency)
    if limit is not None and amount > limit:
        raise AmountValidationError(
            f"Amount {currency} {amount} exceeds scheme limit of {currency} {limit}"
        )


def requires_edd(amount: Decimal, currency: str) -> bool:
    """Return True if amount meets or exceeds EDD threshold (I-04)."""
    threshold = EDD_THRESHOLDS.get(currency, Decimal("10000"))
    return amount >= threshold


def requires_mlro_escalation(amount: Decimal, currency: str) -> bool:
    """Return True if amount meets or exceeds high-value threshold (I-04)."""
    threshold = HIGH_VALUE_THRESHOLDS.get(currency, Decimal("50000"))
    return amount >= threshold
