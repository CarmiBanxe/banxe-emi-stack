"""
services/swift_correspondent/charges_calculator.py
SWIFT Charges Calculator
IL-SWF-01 | Sprint 34 | Phase 47

FCA: PSR 2017, MLR 2017 Reg.28
Trust Zone: RED

SHA/BEN/OUR charge codes. All amounts Decimal (I-22).
EDD surcharge ≥£10k (I-04). AML regulatory cap.
"""

from __future__ import annotations

from decimal import Decimal
import logging

from services.swift_correspondent.models import ChargeCode

logger = logging.getLogger(__name__)

SHA_FEE_GBP = Decimal("25.00")
BEN_FEE_GBP = Decimal("0.00")
OUR_FEE_BASE_GBP = Decimal("35.00")
OUR_FEE_PCT = Decimal("0.001")  # 0.1% of amount
AML_EDD_THRESHOLD = Decimal("10000")  # I-04


class ChargesCalculator:
    """Calculates SWIFT transaction charges (SHA/BEN/OUR).

    All amounts as Decimal (I-22). EDD surcharge applied
    for amounts >= £10k (I-04). Charge breakdown stored per message.
    """

    def __init__(self) -> None:
        """Initialise calculator with empty charge records."""
        self._charges: dict[str, dict[str, Decimal]] = {}

    def calculate_charges(
        self, message_id: str, charge_code: ChargeCode, amount: Decimal
    ) -> dict[str, Decimal]:
        """Calculate SWIFT charges based on charge code and amount.

        I-22: all values as Decimal.
        SHA: sender pays £25 flat.
        BEN: beneficiary pays, sender pays £0.
        OUR: sender pays £35 + 0.1% of amount.

        Args:
            message_id: SWIFT message ID.
            charge_code: SHA/BEN/OUR charge allocation.
            amount: Transfer amount (Decimal, I-22).

        Returns:
            Dict of Decimal charge components.
        """
        if charge_code == ChargeCode.SHA:
            sender_fee = SHA_FEE_GBP
            beneficiary_fee = Decimal("0.00")
        elif charge_code == ChargeCode.BEN:
            sender_fee = BEN_FEE_GBP
            beneficiary_fee = amount * Decimal("0.001")
        else:  # OUR
            sender_fee = OUR_FEE_BASE_GBP + (amount * OUR_FEE_PCT)
            beneficiary_fee = Decimal("0.00")

        breakdown = {
            "sender_fee": sender_fee,
            "beneficiary_fee": beneficiary_fee,
            "edd_surcharge": Decimal("0.00"),
        }
        self._charges[message_id] = breakdown
        logger.info(
            "Charges calculated message_id=%s charge_code=%s sender_fee=%s",
            message_id,
            charge_code,
            sender_fee,
        )
        return breakdown

    def apply_edd_surcharge(self, amount: Decimal) -> Decimal:
        """Apply EDD surcharge for amounts at or above AML threshold.

        I-04: amount >= £10k → add £10.00 surcharge.

        Args:
            amount: Transfer amount (Decimal, I-22).

        Returns:
            Surcharge amount as Decimal (£10 or £0).
        """
        if amount >= AML_EDD_THRESHOLD:
            logger.info("EDD surcharge applied for amount=%s (I-04)", amount)
            return Decimal("10.00")
        return Decimal("0.00")

    def get_total_charges(
        self, message_id: str, charge_code: ChargeCode, amount: Decimal
    ) -> Decimal:
        """Get total charges including EDD surcharge if applicable.

        I-22: returns Decimal.

        Args:
            message_id: SWIFT message ID.
            charge_code: SHA/BEN/OUR charge code.
            amount: Transfer amount (Decimal, I-22).

        Returns:
            Total charges as Decimal.
        """
        breakdown = self.calculate_charges(message_id, charge_code, amount)
        surcharge = self.apply_edd_surcharge(amount)
        total = breakdown["sender_fee"] + breakdown["beneficiary_fee"] + surcharge
        self._charges[message_id]["edd_surcharge"] = surcharge
        return total

    def get_charges_breakdown(self, message_id: str) -> dict[str, Decimal]:
        """Get stored charge breakdown for a message.

        Args:
            message_id: SWIFT message ID.

        Returns:
            Dict of Decimal charge components, or empty dict if not found.
        """
        return self._charges.get(message_id, {})

    def estimate_correspondent_fees(self, bic: str, currency: str, amount: Decimal) -> Decimal:
        """Estimate correspondent bank fees (stub, I-22).

        BT-003: live fee schedule not yet integrated.

        Args:
            bic: Correspondent BIC.
            currency: ISO 4217 currency code.
            amount: Transfer amount (Decimal, I-22).

        Returns:
            Estimated correspondent fee as Decimal (£15.00 stub).
        """
        logger.info(
            "Estimating correspondent fees bic=%s currency=%s amount=%s (stub BT-003)",
            bic,
            currency,
            amount,
        )
        return Decimal("15.00")
