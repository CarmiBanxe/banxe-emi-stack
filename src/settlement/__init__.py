"""Banxe EMI — Settlement reconciliation module (GAP-010 D-recon).

Tri-party engine: payment rails ↔ Midaz GL ledger ↔ safeguarding bank.

Three invariants must hold at end of each business day:
  [I]  RAILS_SETTLED == MIDAZ_GL          — payment rails = internal ledger
  [II] MIDAZ_GL      == SAFEGUARDING_BANK  — internal ledger = external bank
  [III] NET_POSITION == 0                  — no unreconciled float exposure

FCA rules:
  CASS 7.15.17R  — daily internal reconciliation
  CASS 7.15.29R  — alert within 1 business day of discrepancy
  CASS 15.12.4R  — monthly FIN060 from aggregated data
  I-24           — Decimal only, never float for financial amounts
"""

from .reconciler_engine import (
    DiscrepancyReporter,
    LedgerBalance,
    LedgerPort,
    NullDiscrepancyReporter,
    PaymentRailsPort,
    RailsBalance,
    ReconcilerCron,
    ReconLeg,
    SafeguardingBalance,
    SafeguardingBankPort,
    TriPartyReconciler,
    TriPartyResult,
    TriPartyStatus,
)

__all__ = [
    "LedgerBalance",
    "SafeguardingBalance",
    "RailsBalance",
    "ReconLeg",
    "TriPartyResult",
    "TriPartyStatus",
    "LedgerPort",
    "SafeguardingBankPort",
    "PaymentRailsPort",
    "DiscrepancyReporter",
    "NullDiscrepancyReporter",
    "TriPartyReconciler",
    "ReconcilerCron",
]
