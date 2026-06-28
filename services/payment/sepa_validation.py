"""SEPA scheme-compliance validators — single source of truth (ADR-102).

Pure input validation: no network, no secrets, no side effects. Consumed by the live Modulr
rail (`ModulrPaymentAdapter`) and the SEPA adapters. Previously these lived in
`services/payment/legacy/legacy_sepa_adapter.py` (a legacy module) and were partially duplicated;
consolidated here so production code no longer imports validation from a legacy adapter.

References:
  - IBAN: ISO 13616 — mod-97 check digit (EPC SCT / SCT Inst rulebooks).
  - BIC:  ISO 9362 — SWIFT format (8 or 11 chars).
  - SCT Instant value cap: EPC SCT Inst rulebook — €100,000 per transaction.

I-01: monetary values are Decimal (never float).
"""

from __future__ import annotations

from decimal import Decimal
import re

#: EPC SCT Instant per-transaction value cap (EUR).
SCT_INSTANT_MAX_EUR: Decimal = Decimal("100000.00")

_IBAN_RE = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}")
_BIC_RE = re.compile(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?")


def validate_iban(iban: str) -> bool:
    """Return True iff `iban` passes the ISO 13616 mod-97 check (whitespace-insensitive)."""
    clean = iban.replace(" ", "").upper()
    if not _IBAN_RE.fullmatch(clean):
        return False
    rearranged = clean[4:] + clean[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    return int(numeric) % 97 == 1


def validate_bic(bic: str) -> bool:
    """Return True iff `bic` matches ISO 9362 / SWIFT format (8 or 11 chars)."""
    return bool(_BIC_RE.fullmatch(bic.strip().upper()))


def exceeds_sct_instant_cap(amount: Decimal, *, is_instant: bool) -> bool:
    """Return True iff `amount` exceeds the SCT Instant €100k cap (only when `is_instant`)."""
    return is_instant and amount > SCT_INSTANT_MAX_EUR
