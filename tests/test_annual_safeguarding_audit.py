"""
test_annual_safeguarding_audit.py — Tests for Annual Safeguarding Audit (SP-THIN GAP-058)
EMR 2011 reg.21 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.safeguarding.annual_audit import AnnualSafeguardingAuditBuilder, AuditOpinion
from src.safeguarding.daily_reconciliation import ReconciliationResult, ReconStatus


def _result(status: ReconStatus, diff: str | None = None, day: int = 1) -> ReconciliationResult:
    return ReconciliationResult(
        recon_date=date(2026, 1, day),
        internal_balance_gbp=Decimal("1000000"),
        external_balance_gbp=Decimal("1000000") if status != ReconStatus.PENDING else None,
        difference_gbp=Decimal(diff) if diff is not None else None,
        status=status,
    )


class TestOpinion:
    def test_clean_when_no_breaks(self) -> None:
        results = [_result(ReconStatus.MATCHED, "0", d) for d in range(1, 6)]
        audit = AnnualSafeguardingAuditBuilder().build(2026, results)
        assert audit.opinion is AuditOpinion.CLEAN
        assert audit.is_clean is True

    def test_qualified_on_few_breaks(self) -> None:
        results = [_result(ReconStatus.MATCHED, "0", 1), _result(ReconStatus.BREAK, "-150.00", 2)]
        audit = AnnualSafeguardingAuditBuilder().build(2026, results)
        assert audit.opinion is AuditOpinion.QUALIFIED
        assert audit.max_break_gbp == Decimal("150.00")

    def test_adverse_on_systemic_breaks(self) -> None:
        results = [_result(ReconStatus.BREAK, "-10.00", d) for d in range(1, 8)]  # 7 > 5
        audit = AnnualSafeguardingAuditBuilder().build(2026, results)
        assert audit.opinion is AuditOpinion.ADVERSE


class TestCoverage:
    def test_coverage_pct(self) -> None:
        results = [_result(ReconStatus.MATCHED, "0", 1) for _ in range(73)]
        audit = AnnualSafeguardingAuditBuilder().build(2026, results, expected_days=365)
        assert audit.coverage_pct == Decimal("20.0")
        assert audit.days_covered == 73

    def test_counts_by_status(self) -> None:
        results = [
            _result(ReconStatus.MATCHED, "0", 1),
            _result(ReconStatus.BREAK, "-5.00", 2),
            _result(ReconStatus.PENDING, None, 3),
        ]
        audit = AnnualSafeguardingAuditBuilder().build(2026, results)
        assert (audit.days_matched, audit.days_break, audit.days_pending) == (1, 1, 1)
