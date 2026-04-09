"""
bankstatement_parser.py — ISO 20022 CAMT.053 / MT940 parser wrapper
FCA CASS 7.15 P0 | banxe-emi-stack

Phase 1: CSV placeholder (already in statement_fetcher.py)
Phase 2 (adorsys PSD2 gateway): CAMT.053 XML parsing via python-iso20022
          or bankstatementparser PyPI library.

This module wraps the external bankstatementparser library and normalises
its output into StatementBalance dataclasses for use by ReconciliationEngine.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from services.recon.statement_fetcher import StatementBalance

# Account IBAN → internal Midaz UUID mapping (ADR-013)
IBAN_TO_ACCOUNT_ID: dict[str, str] = {
    # Populated at runtime via env or config — do not hardcode IBANs in source
    os.environ.get("SAFEGUARDING_OPERATIONAL_IBAN", ""): os.environ.get(
        "SAFEGUARDING_OPERATIONAL_ACCOUNT", "019d6332-f274-709a-b3a7-983bc8745886"
    ),
    os.environ.get("SAFEGUARDING_CLIENT_FUNDS_IBAN", ""): os.environ.get(
        "SAFEGUARDING_CLIENT_FUNDS_ACCOUNT", "019d6332-da7f-752f-b9fd-fa1c6fc777ec"
    ),
}


def parse_camt053(xml_path: Path) -> list[StatementBalance]:
    """
    Parse a CAMT.053 XML file and return per-account closing balances.

    Requires: pip install bankstatementparser
    Falls back to empty list if library not installed (Phase 1 behaviour).
    """
    try:
        from bankstatementparser import CamtParser  # type: ignore
    except ImportError:
        # Phase 1 — library not yet installed, CSV path used instead
        return []

    parser = CamtParser(str(xml_path))
    statements = parser.parse()

    balances: list[StatementBalance] = []
    for stmt in statements:
        iban = getattr(stmt, "iban", "") or ""
        account_id = IBAN_TO_ACCOUNT_ID.get(iban)
        if not account_id:
            continue

        # Closing balance = CLBD entry in CAMT.053
        closing_balance = _decimal_from_amount(stmt.closing_balance)
        currency = getattr(stmt, "currency", "GBP")
        stmt_date = _extract_date(stmt)

        balances.append(
            StatementBalance(
                account_id=account_id,
                currency=currency,
                balance=closing_balance,
                statement_date=stmt_date,
                source_file=xml_path.name,
            )
        )

    return balances


def parse_mt940(mt940_path: Path) -> list[StatementBalance]:
    """
    Parse an MT940 SWIFT file (legacy Barclays format).

    Requires: pip install mt940
    """
    try:
        import mt940  # type: ignore
    except ImportError:
        return []

    transactions = mt940.models.Transactions()
    with mt940_path.open("rb") as f:
        transactions.parse(f.read())

    balances: list[StatementBalance] = []
    if transactions.data:
        account_id_str = str(transactions.data.get("account_identification", ""))
        account_id = IBAN_TO_ACCOUNT_ID.get(account_id_str, "")
        if account_id:
            final_balance = transactions.data.get("final_closing_balance")
            if final_balance:
                balances.append(
                    StatementBalance(
                        account_id=account_id,
                        currency=str(final_balance.amount.currency),
                        balance=Decimal(str(final_balance.amount.amount)),
                        statement_date=final_balance.date.date()
                        if hasattr(final_balance.date, "date")
                        else date.today(),
                        source_file=mt940_path.name,
                    )
                )
    return balances


# ── helpers ───────────────────────────────────────────────────────────────────


def _decimal_from_amount(amount) -> Decimal:
    """Convert library amount type to Decimal (never float — I-28)."""
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount))


def _extract_date(stmt) -> date:
    """Extract statement date from parsed statement object."""
    d = getattr(stmt, "closing_date", None) or getattr(stmt, "creation_date", None)
    if d is None:
        return date.today()
    if hasattr(d, "date"):
        return d.date()
    if isinstance(d, date):
        return d
    return date.today()
