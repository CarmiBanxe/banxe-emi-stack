"""
services/beneficiary_management/payment_rail_router.py — Payment rail selection
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

from services.beneficiary_management.models import PaymentRail, PaymentRailSelection

_FPS_MAX = Decimal("250000.00")

# EU countries for SEPA (simplified list)
_SEPA_COUNTRIES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IS",
        "IE",
        "IT",
        "LV",
        "LI",
        "LT",
        "LU",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
        "CH",
    }
)

_RAIL_DETAILS: dict[PaymentRail, PaymentRailSelection] = {
    PaymentRail.FPS: PaymentRailSelection(
        rail=PaymentRail.FPS,
        estimated_settlement="instant",
        fee_indicator="low",
        currency="GBP",
        max_amount=_FPS_MAX,
    ),
    PaymentRail.BACS: PaymentRailSelection(
        rail=PaymentRail.BACS,
        estimated_settlement="T+2",
        fee_indicator="low",
        currency="GBP",
    ),
    PaymentRail.CHAPS: PaymentRailSelection(
        rail=PaymentRail.CHAPS,
        estimated_settlement="same-day",
        fee_indicator="high",
        currency="GBP",
    ),
    PaymentRail.SEPA: PaymentRailSelection(
        rail=PaymentRail.SEPA,
        estimated_settlement="T+1",
        fee_indicator="low",
        currency="EUR",
    ),
    PaymentRail.SWIFT: PaymentRailSelection(
        rail=PaymentRail.SWIFT,
        estimated_settlement="T+5",
        fee_indicator="high",
        currency="*",
    ),
}


class PaymentRailRouter:
    def route(
        self,
        amount: Decimal,
        currency: str,
        destination_country: str,
    ) -> dict[str, object]:
        """Select optimal payment rail based on amount, currency, and destination.

        Rules (PSR 2017, FPS scheme, CHAPS scheme):
        - FPS: GBP + UK + amount ≤ £250k → instant
        - CHAPS: GBP + UK + amount > £250k → same-day
        - BACS: GBP + UK (fallback batch)
        - SEPA: EUR + SEPA country → T+1
        - SWIFT: international fallback
        """
        if amount <= Decimal("0"):
            raise ValueError("Payment amount must be positive (I-01)")
        country = destination_country.upper()
        ccy = currency.upper()

        if ccy == "GBP" and country == "GB":
            if amount <= _FPS_MAX:
                rail = PaymentRail.FPS
            else:
                rail = PaymentRail.CHAPS
        elif ccy == "EUR" and country in _SEPA_COUNTRIES:
            rail = PaymentRail.SEPA
        else:
            rail = PaymentRail.SWIFT

        details = _RAIL_DETAILS[rail]
        return {
            "rail": rail.value,
            "amount": str(amount),
            "currency": ccy,
            "destination_country": country,
            "estimated_settlement": details.estimated_settlement,
            "fee_indicator": details.fee_indicator,
            "max_amount": str(details.max_amount) if details.max_amount else None,
        }

    def get_rail_details(self, rail: PaymentRail | str) -> dict[str, object]:
        r = rail if isinstance(rail, PaymentRail) else PaymentRail(rail)
        details = _RAIL_DETAILS[r]
        return {
            "rail": r.value,
            "estimated_settlement": details.estimated_settlement,
            "fee_indicator": details.fee_indicator,
            "currency": details.currency,
            "max_amount": str(details.max_amount) if details.max_amount else None,
        }

    def list_rails(self) -> dict[str, object]:
        return {
            "count": len(_RAIL_DETAILS),
            "rails": [
                {
                    "rail": r.value,
                    "estimated_settlement": d.estimated_settlement,
                    "fee_indicator": d.fee_indicator,
                }
                for r, d in _RAIL_DETAILS.items()
            ],
        }
