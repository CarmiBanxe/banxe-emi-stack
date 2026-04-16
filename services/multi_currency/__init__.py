"""
services/multi_currency — Multi-Currency Ledger Enhancement.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Provides multi-currency account management, balance engine, nostro reconciliation,
currency routing, and conversion tracking for EMI operations across 10 currencies.

Key invariants enforced:
  - I-01: All monetary amounts use Decimal — never float.
  - I-05: API layer serialises amounts as strings.
  - I-24: Append-only audit trail for all ledger events.
  - max_currencies = 10 per account.
  - Nostro tolerance = Decimal("1.00") (£1, broader than internal 1p).
  - Conversion fee = 0.2% (Decimal("0.002")).
"""
