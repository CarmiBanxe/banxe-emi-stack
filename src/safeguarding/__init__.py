"""Banxe EMI — Safeguarding module (CASS 15 / FCA PS23/3).

Four core components:
  daily_reconciliation  — internal ledger vs external bank balance comparison
  breach_detector       — >3 day discrepancy streak → mandatory FCA alert
  fin060_generator      — monthly FCA FIN060 return data structure
  audit_trail           — ClickHouse immutable append-only event log

FCA references:
  CASS 7.15.17R  — daily reconciliation requirement
  CASS 15.12.4R  — monthly FIN060 return
  CASS 10A.3.1R  — 48h resolution pack
  PS23/3         — strengthened safeguarding rules (7 May 2026 deadline)
"""

from .audit_trail import AuditEvent, AuditTrail
from .breach_detector import BreachAlert, BreachDetector, BreachSeverity
from .daily_reconciliation import DailyReconciliation, ReconciliationResult, ReconStatus
from .fin060_generator import FIN060Generator, FIN060Return

__all__ = [
    "DailyReconciliation",
    "ReconciliationResult",
    "ReconStatus",
    "BreachDetector",
    "BreachAlert",
    "BreachSeverity",
    "FIN060Generator",
    "FIN060Return",
    "AuditTrail",
    "AuditEvent",
]
