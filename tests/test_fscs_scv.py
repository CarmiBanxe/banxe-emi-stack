"""
test_fscs_scv.py — Tests for FSCS Single Customer View (SP-THIN GAP-024)
FSCS / PRA SS18/15 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.resolution.fscs_scv import (
    FSCS_LIMIT_GBP,
    DepositorBalance,
    FscsScvReportBuilder,
    InMemoryDepositorRepository,
)


def _bal(cid: str, amount: str, *, eligible: bool = True, acc: str = "a1") -> DepositorBalance:
    return DepositorBalance(
        customer_id=cid, currency="GBP", balance=Decimal(amount), eligible=eligible, account_id=acc
    )


def _builder(balances: list[DepositorBalance]) -> FscsScvReportBuilder:
    return FscsScvReportBuilder(InMemoryDepositorRepository(balances))


class TestEligibility:
    def test_under_limit_fully_protected(self) -> None:
        report = _builder([_bal("c1", "10000")]).build(datetime.now(UTC))
        assert report.records[0].protected_amount == Decimal("10000")
        assert report.total_eligible_depositors == 1

    def test_over_limit_capped_at_fscs(self) -> None:
        report = _builder([_bal("c1", "120000")]).build()
        assert report.records[0].protected_amount == FSCS_LIMIT_GBP
        assert report.records[0].aggregate_balance == Decimal("120000")

    def test_ineligible_zero_protected(self) -> None:
        report = _builder([_bal("c1", "50000", eligible=False)]).build()
        assert report.records[0].protected_amount == Decimal("0")
        assert report.total_eligible_depositors == 0


class TestAggregation:
    def test_accounts_aggregate_then_cap(self) -> None:
        report = _builder([_bal("c1", "60000", acc="a1"), _bal("c1", "40000", acc="a2")]).build()
        rec = report.records[0]
        assert rec.aggregate_balance == Decimal("100000")
        assert rec.protected_amount == FSCS_LIMIT_GBP  # capped after aggregation

    def test_total_protected_sums_records(self) -> None:
        report = _builder([_bal("c1", "10000"), _bal("c2", "90000")]).build()
        assert report.total_protected == Decimal("10000") + FSCS_LIMIT_GBP


class TestManifest:
    def test_manifest_fields(self) -> None:
        m = _builder([_bal("c1", "100")]).build().to_manifest()
        assert m["pra_rule"] == "PRA SS18/15"
        assert m["fscs_limit"] == "85000.00"
        assert m["record_count"] == 1
