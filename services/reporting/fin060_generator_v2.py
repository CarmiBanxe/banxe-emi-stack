"""
services/reporting/fin060_generator_v2.py — FIN060Generator V2
IL-FIN060-01 | Phase 51C | Sprint 36
Generates FIN060 regulatory reports with HITL gate (CFO approval required).
Does NOT overwrite fin060_generator.py (backward compat).
Invariants: I-01 (Decimal), I-24 (append-only), I-27 (HITL)
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import uuid

from services.reporting.report_models import (
    FIN060Entry,
    FIN060Report,
    InMemoryReportStore,
    ReportStorePort,
)


@dataclass(frozen=True)
class HITLProposal:
    """HITL gate — AI proposes, human decides (I-27)."""

    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class FIN060Generator:
    """
    Generates FIN060 regulatory reports.
    All monetary values use Decimal (I-01).
    Reports are append-only (I-24).
    generate_fin060 always returns HITLProposal (L4 HITL, CFO).
    """

    def __init__(self, store: ReportStorePort | None = None) -> None:
        self._store = store or InMemoryReportStore()

    def generate_fin060(
        self,
        month: int,
        year: int,
        ledger_data: list[dict],
    ) -> HITLProposal:
        """
        Generate FIN060 report for given month/year from ledger data.
        Validates month (1-12) and year (>=2020).
        Appends DRAFT report to store (I-24).
        Returns HITLProposal (L4 HITL, CFO) — never auto-submits (I-27).
        """
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month: {month}. Must be 1-12.")
        if year < 2020:
            raise ValueError(f"Invalid year: {year}. Must be >= 2020.")

        # Calculate period bounds
        last_day = calendar.monthrange(year, month)[1]
        period_start = f"{year}-{month:02d}-01"
        period_end = f"{year}-{month:02d}-{last_day:02d}"

        # Build entries and aggregate totals (I-01: Decimal only)
        entries: list[FIN060Entry] = []
        total_safeguarded = Decimal("0")
        total_operational = Decimal("0")

        for item in ledger_data:
            account_type = item.get("account_type", "operational")
            balance = Decimal(str(item.get("balance", "0")))
            currency = item.get("currency", "GBP")
            entry_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]

            entries.append(
                FIN060Entry(
                    entry_id=entry_id,
                    account_type=account_type,
                    currency=currency,
                    balance=balance,
                    period_start=period_start,
                    period_end=period_end,
                )
            )

            if account_type == "safeguarding":
                total_safeguarded += balance
            else:
                total_operational += balance

        report_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        report = FIN060Report(
            report_id=report_id,
            month=month,
            year=year,
            total_safeguarded_gbp=total_safeguarded,
            total_operational_gbp=total_operational,
            entries=tuple(entries),
            status="DRAFT",
            generated_at=datetime.now(UTC).isoformat(),
        )
        self._store.append(report)  # I-24: append-only

        entity_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        return HITLProposal(
            action="generate_fin060",
            entity_id=entity_id,
            requires_approval_from="CFO",
            reason=f"FIN060 report generated for {year}-{month:02d} (report_id={report_id})",
            autonomy_level="L4",
        )

    def approve_report(self, report_id: str, approved_by: str) -> HITLProposal:
        """
        L4 HITL — propose approval. Never auto-approves (I-27).
        Returns HITLProposal; CFO must confirm.
        """
        entity_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        return HITLProposal(
            action="approve_fin060",
            entity_id=entity_id,
            requires_approval_from="CFO",
            reason=f"FIN060 approval requested for {report_id} by {approved_by}",
            autonomy_level="L4",
        )

    def submit_to_regdata(self, report_id: str) -> None:
        """BT-006 stub — RegData API not yet integrated."""
        raise NotImplementedError("BT-006: RegData API not integrated")

    def get_report(self, month: int, year: int) -> FIN060Report | None:
        """L1 auto — retrieve report by period."""
        return self._store.get_by_period(month, year)

    def get_dashboard(self) -> dict:
        """L1 auto — return dashboard summary."""
        reports = self._store.list_reports()
        total_safeguarded = sum(
            (r.total_safeguarded_gbp for r in reports),
            Decimal("0"),
        )
        pending = sum(1 for r in reports if r.status == "DRAFT")
        last_submission: str | None = None
        if reports:
            last = reports[-1]
            last_submission = f"{last.year}-{last.month:02d}"

        return {
            "total_reports": len(reports),
            "pending_approval": pending,
            "last_submission": last_submission,
            "safeguarded_gbp": str(total_safeguarded),  # I-01: Decimal as string
        }
