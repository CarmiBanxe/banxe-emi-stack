"""FIN060 Generator — CASS 15.12.4R monthly safeguarding return.

Produces the structured data for the FCA FIN060 monthly return.
The return must be submitted via FCA RegData / Gabriel portal within
15 business days of the reference month end.

FCA rules:
  CASS 15.12.4R   — monthly safeguarding return obligation
  CASS 15.12.9G   — guidance on completing the return
  PS23/3          — enhanced requirements from 7 May 2026

Output format:
  FIN060Return dataclass — all monetary values as Decimal (GBP)
  .to_dict()            — serialisable dict for JSON / PDF template
  .to_csv_row()         — single CSV row for RegData bulk upload

Usage:
    gen = FIN060Generator(
        institution_name="Banxe Ltd",
        frn="987654",
        reference_month=date(2026, 4, 1),
    )
    ret = gen.build(
        total_client_funds_gbp=Decimal("1500000.00"),
        safeguarding_balance_gbp=Decimal("1500050.00"),
        shortfall_gbp=Decimal("0"),
        num_safeguarding_accounts=2,
        safeguarding_bank="Barclays Bank PLC",
        daily_recon_count=22,
        daily_recon_breaks=0,
        notes="April 2026 return — all reconciliations matched.",
    )
    print(ret.to_dict())
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
import io
import json
import logging

logger = logging.getLogger(__name__)

# FCA return version — increment when FCA changes the template
FIN060_VERSION = "2026.1"


@dataclass
class FIN060Return:
    """FCA FIN060 monthly safeguarding return.

    All monetary fields are in GBP to 2 decimal places.
    Submitted by CFO via FCA RegData portal (non-delegable to AI).
    """

    # Header
    institution_name: str
    frn: str  # FCA Firm Reference Number
    reference_month: date  # First day of the reference month
    return_version: str = FIN060_VERSION
    prepared_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Section A — Client fund totals
    total_client_funds_gbp: Decimal = Decimal("0")  # Sum of all e-money client balances
    safeguarding_balance_gbp: Decimal = Decimal("0")  # Closing balance of safeguarding account(s)
    surplus_gbp: Decimal = Decimal("0")  # = safeguarding - client_funds (≥0 = good)
    shortfall_gbp: Decimal = Decimal("0")  # Positive value = regulatory breach

    # Section B — Safeguarding accounts
    num_safeguarding_accounts: int = 0
    safeguarding_bank: str = ""  # e.g. "Barclays Bank PLC"
    account_designation: str = "CLIENT FUNDS — BANXE LTD"  # Account name per CASS 15.3

    # Section C — Daily reconciliation statistics
    daily_recon_count: int = 0  # Number of trading days in month
    daily_recon_breaks: int = 0  # Days with reconciliation break
    longest_break_streak: int = 0  # Max consecutive break days
    fca_breach_notified: bool = False  # Whether FCA was formally notified

    # Section D — Narrative
    notes: str = ""

    @property
    def month_label(self) -> str:
        return self.reference_month.strftime("%B %Y")

    @property
    def is_compliant(self) -> bool:
        return self.shortfall_gbp == Decimal("0") and not self.fca_breach_notified

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert Decimal → str for JSON safety; date/datetime → ISO
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
            elif isinstance(v, date | datetime):
                d[k] = v.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_csv_row(self) -> str:
        """Single CSV row for FCA RegData bulk upload."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                self.frn,
                self.institution_name,
                self.reference_month.strftime("%Y-%m"),
                str(self.total_client_funds_gbp),
                str(self.safeguarding_balance_gbp),
                str(self.surplus_gbp),
                str(self.shortfall_gbp),
                self.num_safeguarding_accounts,
                self.safeguarding_bank,
                self.daily_recon_count,
                self.daily_recon_breaks,
                self.longest_break_streak,
                "Y" if self.fca_breach_notified else "N",
                self.notes,
                self.return_version,
                self.prepared_at.isoformat(),
            ]
        )
        return buf.getvalue().strip()


class FIN060Generator:
    """Build the FIN060 monthly return data structure.

    Args:
        institution_name: Legal name of the EMI (e.g. "Banxe Ltd")
        frn: FCA Firm Reference Number
        reference_month: date(year, month, 1) — first day of month being reported
    """

    def __init__(
        self,
        institution_name: str,
        frn: str,
        reference_month: date,
    ) -> None:
        self.institution_name = institution_name
        self.frn = frn
        self.reference_month = reference_month

    def build(
        self,
        total_client_funds_gbp: Decimal,
        safeguarding_balance_gbp: Decimal,
        num_safeguarding_accounts: int,
        safeguarding_bank: str,
        daily_recon_count: int,
        daily_recon_breaks: int,
        shortfall_gbp: Decimal | None = None,
        longest_break_streak: int = 0,
        fca_breach_notified: bool = False,
        notes: str = "",
        account_designation: str = "CLIENT FUNDS — BANXE LTD",
    ) -> FIN060Return:
        """Construct and validate the FIN060 return.

        Surplus/shortfall is calculated automatically from the supplied balances.
        Pass shortfall_gbp=None to auto-calculate from balances (normal case).
        Pass shortfall_gbp=Decimal("X") to override (e.g. if timing difference exists).
        """
        surplus = safeguarding_balance_gbp - total_client_funds_gbp

        if shortfall_gbp is None:
            # Auto-calculate: a negative surplus is a shortfall
            computed_shortfall = max(Decimal("0"), -surplus)
        else:
            computed_shortfall = shortfall_gbp

        if computed_shortfall > Decimal("0"):
            logger.critical(
                "FIN060 %s: SHORTFALL of £%s — FCA regulatory breach. "
                "CFO must notify FCA within 1 business day.",
                self.reference_month.strftime("%Y-%m"),
                computed_shortfall,
            )

        ret = FIN060Return(
            institution_name=self.institution_name,
            frn=self.frn,
            reference_month=self.reference_month,
            total_client_funds_gbp=total_client_funds_gbp,
            safeguarding_balance_gbp=safeguarding_balance_gbp,
            surplus_gbp=max(Decimal("0"), surplus),
            shortfall_gbp=computed_shortfall,
            num_safeguarding_accounts=num_safeguarding_accounts,
            safeguarding_bank=safeguarding_bank,
            account_designation=account_designation,
            daily_recon_count=daily_recon_count,
            daily_recon_breaks=daily_recon_breaks,
            longest_break_streak=longest_break_streak,
            fca_breach_notified=fca_breach_notified,
            notes=notes,
        )

        logger.info(
            "FIN060 built: %s | Client funds: £%s | Safeguarding: £%s | "
            "Surplus: £%s | Shortfall: £%s | Compliant: %s",
            ret.month_label,
            total_client_funds_gbp,
            safeguarding_balance_gbp,
            ret.surplus_gbp,
            ret.shortfall_gbp,
            ret.is_compliant,
        )
        return ret
