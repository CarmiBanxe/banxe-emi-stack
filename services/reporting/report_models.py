"""
services/reporting/report_models.py — FIN060 report data models
IL-FIN060-01 | Phase 51C | Sprint 36
Does NOT overwrite fin060_generator.py (backward compat).
Invariants: I-01 (Decimal), I-24 (append-only)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

# ── Data Models ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FIN060Entry:
    """Immutable ledger entry for FIN060 report (I-24)."""

    entry_id: str
    account_type: str  # safeguarding | operational
    currency: str
    balance: Decimal  # I-01: never float
    period_start: str
    period_end: str


@dataclass(frozen=True)
class FIN060Report:
    """Immutable FIN060 report (I-24)."""

    report_id: str
    month: int
    year: int
    total_safeguarded_gbp: Decimal  # I-01
    total_operational_gbp: Decimal  # I-01
    entries: tuple[FIN060Entry, ...]
    status: str  # DRAFT | APPROVED | SUBMITTED
    generated_at: str
    approved_by: str | None = None


# ── Protocol (Port) ───────────────────────────────────────────────────────────


class ReportStorePort(Protocol):
    def append(self, report: FIN060Report) -> None: ...
    def list_reports(self) -> list[FIN060Report]: ...
    def get_by_period(self, month: int, year: int) -> FIN060Report | None: ...


# ── InMemory Adapter (test/sandbox) ──────────────────────────────────────────


class InMemoryReportStore:
    """Append-only in-memory FIN060 report store (I-24). No delete/update methods."""

    def __init__(self) -> None:
        self._reports: list[FIN060Report] = []

    def append(self, report: FIN060Report) -> None:
        self._reports.append(report)

    def list_reports(self) -> list[FIN060Report]:
        return list(self._reports)

    def get_by_period(self, month: int, year: int) -> FIN060Report | None:
        for r in self._reports:
            if r.month == month and r.year == year:
                return r
        return None
