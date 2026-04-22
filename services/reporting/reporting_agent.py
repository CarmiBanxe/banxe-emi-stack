"""
services/reporting/reporting_agent.py — ReportingAgent
IL-FIN060-01 | Phase 51C | Sprint 36
Orchestrates FIN060 generation with HITL gate (CFO).
Invariants: I-01 (Decimal), I-24 (append-only), I-27 (HITL)
"""

from __future__ import annotations

from services.reporting.fin060_generator_v2 import FIN060Generator, HITLProposal
from services.reporting.report_models import FIN060Report, InMemoryReportStore, ReportStorePort


class ReportingAgent:
    """
    Orchestrates FIN060 regulatory reporting.
    All generate/approve operations return HITLProposal (L4 HITL, CFO).
    """

    def __init__(self, store: ReportStorePort | None = None) -> None:
        _store = store or InMemoryReportStore()
        self._generator = FIN060Generator(store=_store)

    def run_monthly_fin060(
        self,
        month: int,
        year: int,
        ledger_data: list[dict] | None = None,
    ) -> HITLProposal:
        """L4 HITL — generate FIN060 report. Always returns HITLProposal (CFO)."""
        return self._generator.generate_fin060(month, year, ledger_data or [])

    def approve_and_submit(self, report_id: str, approved_by: str) -> HITLProposal:
        """L4 HITL — approve report. Always returns HITLProposal (CFO)."""
        return self._generator.approve_report(report_id, approved_by)

    def get_report(self, month: int, year: int) -> FIN060Report | None:
        """L1 auto — retrieve report by period."""
        return self._generator.get_report(month, year)

    def get_dashboard(self) -> dict:
        """L1 auto — return dashboard summary."""
        return self._generator.get_dashboard()
