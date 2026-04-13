"""Banxe EMI — Fee Engine (GAP-019 D-fee).

Calculates transaction fees per configurable fee schedules.

FCA compliance:
  - All amounts Decimal (I-24, never float)
  - Fee schedule changes logged to audit trail
  - CFO HITL gate for schedule amendments
  - Consumer Duty PS22/9: fair value assessment required per product
"""

from .fee_engine import (
    FeeCalculation,
    FeeEngine,
    FeeRule,
    FeeSchedule,
    FeeType,
    TransactionContext,
)

__all__ = [
    "FeeType",
    "FeeRule",
    "FeeSchedule",
    "TransactionContext",
    "FeeCalculation",
    "FeeEngine",
]
