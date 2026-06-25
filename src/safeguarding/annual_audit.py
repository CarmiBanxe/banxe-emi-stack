"""
annual_audit.py — Annual Safeguarding Audit report
SP-THIN GAP-058 | EMR 2011 reg.21 / FCA safeguarding audit | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
The safeguarding regime requires an annual safeguarding audit: an opinion on
whether client funds were safeguarded throughout the year. This aggregates a
year of daily reconciliation results (from `daily_reconciliation.py`) and any
breaks into an Annual Safeguarding Audit report with an audit opinion. It does
NOT reimplement the daily reconciliation — it consumes its results.

FCA rules:
  - EMR 2011 reg.21: safeguarding of relevant funds
  - Amounts are GBP and ALWAYS Decimal (I-05)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from src.safeguarding.daily_reconciliation import ReconciliationResult, ReconStatus


class AuditOpinion(str, Enum):
    CLEAN = "CLEAN"  # no recon breaks all year
    QUALIFIED = "QUALIFIED"  # 1..N breaks, resolved
    ADVERSE = "ADVERSE"  # systemic breaks (> threshold)


@dataclass(frozen=True)
class AnnualSafeguardingAudit:
    year: int
    generated_at: datetime
    days_covered: int
    days_matched: int
    days_break: int
    days_pending: int
    coverage_pct: Decimal
    max_break_gbp: Decimal
    opinion: AuditOpinion
    fca_rule: str = "EMR 2011 reg.21"

    @property
    def is_clean(self) -> bool:
        return self.opinion == AuditOpinion.CLEAN


# > this many recon breaks in a year ⇒ adverse opinion.
_ADVERSE_BREAK_COUNT = 5


class AnnualSafeguardingAuditBuilder:
    """Builds the Annual Safeguarding Audit from a year of daily recon results."""

    def build(
        self,
        year: int,
        results: list[ReconciliationResult],
        *,
        expected_days: int = 365,
    ) -> AnnualSafeguardingAudit:
        matched = sum(1 for r in results if r.status == ReconStatus.MATCHED)
        breaks = sum(1 for r in results if r.status == ReconStatus.BREAK)
        pending = sum(1 for r in results if r.status == ReconStatus.PENDING)
        days = len(results)
        coverage = (
            (Decimal(days) / Decimal(expected_days) * Decimal("100")).quantize(Decimal("0.1"))
            if expected_days > 0
            else Decimal("0")
        )
        max_break = max(
            (
                abs(r.difference_gbp)
                for r in results
                if r.status == ReconStatus.BREAK and r.difference_gbp is not None
            ),
            default=Decimal("0"),
        )
        if breaks == 0:
            opinion = AuditOpinion.CLEAN
        elif breaks > _ADVERSE_BREAK_COUNT:
            opinion = AuditOpinion.ADVERSE
        else:
            opinion = AuditOpinion.QUALIFIED
        return AnnualSafeguardingAudit(
            year=year,
            generated_at=datetime.now(UTC),
            days_covered=days,
            days_matched=matched,
            days_break=breaks,
            days_pending=pending,
            coverage_pct=coverage,
            max_break_gbp=max_break,
            opinion=opinion,
        )
