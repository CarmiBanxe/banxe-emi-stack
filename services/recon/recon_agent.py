"""
services/recon/recon_agent.py — ReconAgent
IL-REC-01 | Phase 51B | Sprint 36
Orchestrates daily reconciliation with HITL gate for breaches > £100.
Invariants: I-01 (Decimal), I-24 (append-only), I-27 (HITL)
"""

from __future__ import annotations

from datetime import date

from services.recon.reconciliation_engine_v2 import (
    BREACH_HITL_THRESHOLD,
    HITLProposal,
    InMemoryReconStore,
    ReconciliationEngineV2,
    ReconciliationReport,
    ReconStorePort,
    StatementEntry,
)


class ReconAgent:
    """
    Orchestrates daily reconciliation.
    - Breach ≤ £100: returns ReconciliationReport (L1/L2 auto)
    - Breach > £100: returns HITLProposal (L4 HITL, COMPLIANCE_OFFICER)
    """

    def __init__(self, store: ReconStorePort | None = None) -> None:
        self._store = store or InMemoryReconStore()
        self._engine = ReconciliationEngineV2(self._store)

    def run_daily_recon(
        self,
        date_str: str,
        ledger_entries: list[dict] | None = None,
        statement_entries: list[StatementEntry] | None = None,
    ) -> ReconciliationReport | HITLProposal:
        """
        Run daily reconciliation.
        If net discrepancy > BREACH_HITL_THRESHOLD → return HITLProposal (L4).
        Otherwise → return ReconciliationReport (L1).
        """
        recon_date = date.fromisoformat(date_str)
        report = self._engine.run_daily(
            recon_date,
            ledger_entries or [],
            statement_entries or [],
        )

        if report.breach_detected and report.net_discrepancy_gbp > BREACH_HITL_THRESHOLD:
            return self._engine.resolve_breach(report.report_id, "recon_agent")

        return report

    def get_report(self, date_str: str) -> ReconciliationReport | None:
        """L1 auto — retrieve report by date."""
        return self._store.get_by_date(date_str)

    def list_unresolved_breaches(self) -> list[ReconciliationReport]:
        """L1 auto — list all reports with breach_detected=True."""
        return self._store.list_breaches()

    def list_all_reports(self) -> list[ReconciliationReport]:
        """L1 auto — list all reconciliation reports."""
        return self._store.list_reports()
