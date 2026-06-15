"""
services/compliance/legacy/_edd.py — Shared EDD threshold logic (I-04).

Single source of truth for Enhanced Due Diligence triggers across all KYC adapters.
Thresholds: £10,000 individual/sole-trader | £50,000 business | PEP always True.
Beneficial ownership gate: ownership_pct ≥ 25% triggers EDD (FATF Rec. 24).

Canon: ADR-025 §15-16 | I-04 | MLR 2017 reg. 33 | FATF Rec. 12
"""

from __future__ import annotations

from decimal import Decimal

_INDIVIDUAL_THRESHOLD: Decimal = Decimal("10000.00")  # I-04 individual + sole trader
_CORPORATE_THRESHOLD: Decimal = Decimal("50000.00")  # I-04 business (KYB)
_UBO_OWNERSHIP_THRESHOLD: Decimal = Decimal("25.00")  # FATF Rec. 24 beneficial owner gate


def is_edd_required(
    *,
    income_gbp: Decimal,
    kyc_type: str,
    is_pep: bool,
    ownership_pct: Decimal | None = None,
) -> bool:
    """
    Return True if Enhanced Due Diligence is required.

    Args:
        income_gbp: Expected transaction volume in GBP (I-04 gate).
        kyc_type: KYCType value string — "INDIVIDUAL", "SOLE_TRADER", or "BUSINESS".
        is_pep: True if the customer is a Politically Exposed Person (I-04).
        ownership_pct: Beneficial ownership percentage (0-100). None = not applicable.
    """
    if is_pep:
        return True
    if ownership_pct is not None and ownership_pct >= _UBO_OWNERSHIP_THRESHOLD:
        return True
    threshold = _CORPORATE_THRESHOLD if kyc_type == "BUSINESS" else _INDIVIDUAL_THRESHOLD
    return income_gbp >= threshold
