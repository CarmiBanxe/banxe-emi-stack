"""Shared reconciliation CORE — regime-agnostic safeguarding mechanics.

This package holds the COMMON, regulation-agnostic reconciliation mechanics that
were previously duplicated across the two safeguarding paths:

  * Router A — ``src.safeguarding.*`` — CASS 15 EMI **aggregate** safeguarding:
    internal-vs-statutory-bank balance, penny-exact tolerance £0.01 → MATCHED/BREAK.
  * Router B — ``services.recon.*`` — CASS 7.15 **line-item** reconciliation +
    HITL breach escalation > £100 → HITLProposal.

CRITICAL BOUNDARY (S6.2):
  The two paths are DIFFERENT regulatory regimes, NOT competing values of one rule.
  This core extracts only the shared *mechanics*. Every regulatory threshold is an
  INPUT, injected by the consuming regime — never unified here:

    * CASS 15   injects threshold=Decimal("0.01"), breach_kind="BREAK"
    * CASS 7.15 injects threshold=Decimal("100"),  breach_kind="HITL"

  The core deliberately knows nothing about which regime calls it. See
  ``docs/architecture/RECON-CORE-BOUNDARY.md`` and ADR-SAF-01.

Invariants: I-01 / I-05 — money is Decimal only; serialised as string, never float.
"""

from __future__ import annotations

from .audit import AuditSink, ReconAuditEvent, emit_recon_audit
from .breach_evaluator import BreachDecision, BreachEvaluator
from .compare import absolute_difference, signed_difference, within_tolerance
from .result import CoreReconResult, evaluate_balances

__all__ = [
    "absolute_difference",
    "signed_difference",
    "within_tolerance",
    "BreachEvaluator",
    "BreachDecision",
    "CoreReconResult",
    "evaluate_balances",
    "ReconAuditEvent",
    "AuditSink",
    "emit_recon_audit",
]
