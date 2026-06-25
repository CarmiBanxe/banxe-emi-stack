"""
fscs_scv.py — FSCS Single Customer View (SCV) reporting
SP-THIN GAP-024 | FSCS / PRA SS18/15 (depositor protection) | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
The FSCS depositor-protection regime requires a Single Customer View (SCV): for
each eligible depositor, the aggregate protected balance (capped at the FSCS
limit, £85,000) plus an eligibility marking, retrievable for a fast payout. This
extends the CASS 10A resolution pack (`resolution_pack.py`) with the FSCS SCV
view used at a resolution / insolvency event.

FCA / PRA rules:
  - PRA SS18/15: Single Customer View file content + production timeframe
  - FSCS limit: £85,000 per eligible depositor
  - Amounts are GBP and ALWAYS Decimal (I-05)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

FSCS_LIMIT_GBP = Decimal("85000.00")


@dataclass
class DepositorBalance:
    """One account balance for a depositor (multiple may aggregate per customer)."""

    customer_id: str
    currency: str
    balance: Decimal
    eligible: bool = True  # FSCS-eligible depositor (e.g. not a credit institution)
    account_id: str | None = None


@dataclass(frozen=True)
class ScvRecord:
    """A depositor's Single Customer View entry."""

    customer_id: str
    aggregate_balance: Decimal  # summed across the depositor's accounts
    protected_amount: Decimal  # min(aggregate, FSCS limit) if eligible else 0
    eligible: bool
    currency: str = "GBP"


@dataclass(frozen=True)
class FscsScvReport:
    generated_at: datetime
    as_of_date: datetime
    records: list[ScvRecord]
    total_protected: Decimal
    total_eligible_depositors: int
    fscs_limit: Decimal = FSCS_LIMIT_GBP
    pra_rule: str = "PRA SS18/15"

    def to_manifest(self) -> dict:
        return {
            "pra_rule": self.pra_rule,
            "generated_at": self.generated_at.isoformat(),
            "as_of_date": self.as_of_date.isoformat(),
            "fscs_limit": str(self.fscs_limit),
            "record_count": len(self.records),
            "total_eligible_depositors": self.total_eligible_depositors,
            "total_protected": str(self.total_protected),
        }


class DepositorRepository(Protocol):
    def get_depositor_balances(self, as_of: datetime) -> list[DepositorBalance]: ...


class InMemoryDepositorRepository:
    """Test/sandbox repository (no ClickHouse dependency)."""

    def __init__(self, balances: list[DepositorBalance] | None = None) -> None:
        self._balances = balances or []

    def get_depositor_balances(self, as_of: datetime) -> list[DepositorBalance]:
        return list(self._balances)


class FscsScvReportBuilder:
    """Builds the FSCS Single Customer View from depositor balances."""

    def __init__(self, repo: DepositorRepository, limit: Decimal = FSCS_LIMIT_GBP) -> None:
        self._repo = repo
        self._limit = limit

    def build(self, as_of: datetime | None = None) -> FscsScvReport:
        as_of = as_of or datetime.now(UTC)
        balances = self._repo.get_depositor_balances(as_of)

        # Aggregate balances per customer; eligibility is AND across their accounts.
        agg: dict[str, DepositorBalance] = {}
        for b in balances:
            cur = agg.get(b.customer_id)
            if cur is None:
                agg[b.customer_id] = DepositorBalance(
                    customer_id=b.customer_id,
                    currency=b.currency,
                    balance=b.balance,
                    eligible=b.eligible,
                )
            else:
                cur.balance += b.balance
                cur.eligible = cur.eligible and b.eligible

        records: list[ScvRecord] = []
        for cid, b in agg.items():
            protected = min(b.balance, self._limit) if b.eligible else Decimal("0")
            records.append(
                ScvRecord(
                    customer_id=cid,
                    aggregate_balance=b.balance,
                    protected_amount=protected,
                    eligible=b.eligible,
                    currency=b.currency,
                )
            )
        records.sort(key=lambda r: r.customer_id)

        total_protected = sum((r.protected_amount for r in records), Decimal("0"))
        eligible_count = sum(1 for r in records if r.eligible)
        return FscsScvReport(
            generated_at=datetime.now(UTC),
            as_of_date=as_of,
            records=records,
            total_protected=total_protected,
            total_eligible_depositors=eligible_count,
            fscs_limit=self._limit,
        )
