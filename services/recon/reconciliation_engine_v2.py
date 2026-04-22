"""
services/recon/reconciliation_engine_v2.py — Reconciliation Engine V2
IL-REC-01 | Phase 51B | Sprint 36 | CASS 7.15
Invariants: I-01 (Decimal), I-24 (append-only), I-27 (HITL proposal)
Does NOT overwrite reconciliation_engine.py (backward compat).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import logging
from typing import Protocol
import uuid

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

RECON_TOLERANCE_GBP: Decimal = Decimal("0.01")
BREACH_HITL_THRESHOLD: Decimal = Decimal("100")


# ── Data Models ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HITLProposal:
    """HITL gate — AI proposes, human decides (I-27)."""

    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


@dataclass(frozen=True)
class StatementEntry:
    """Immutable bank statement entry (I-24)."""

    entry_id: str
    account_iban: str
    amount: Decimal  # I-01: never float
    currency: str
    value_date: str
    description: str
    transaction_ref: str


@dataclass(frozen=True)
class ReconciliationItem:
    """Immutable reconciliation line item (I-24)."""

    item_id: str
    account_iban: str
    ledger_amount: Decimal  # I-01
    statement_amount: Decimal  # I-01
    discrepancy: Decimal  # I-01
    recon_date: str
    status: str  # MATCHED | DISCREPANCY | MISSING_STATEMENT | MISSING_LEDGER


@dataclass(frozen=True)
class ReconciliationReport:
    """Immutable reconciliation report (I-24)."""

    report_id: str
    recon_date: str
    total_ledger_gbp: Decimal  # I-01
    total_statement_gbp: Decimal  # I-01
    net_discrepancy_gbp: Decimal  # I-01
    items: tuple[ReconciliationItem, ...]
    breach_detected: bool
    created_at: str


# ── Protocol (Port) ───────────────────────────────────────────────────────────


class ReconStorePort(Protocol):
    def append(self, report: ReconciliationReport) -> None: ...
    def list_reports(self) -> list[ReconciliationReport]: ...
    def get_by_date(self, recon_date: str) -> ReconciliationReport | None: ...
    def list_breaches(self) -> list[ReconciliationReport]: ...


# ── InMemory Adapter (test/sandbox) ──────────────────────────────────────────


class InMemoryReconStore:
    """Append-only in-memory recon store (I-24). No delete/update methods."""

    def __init__(self) -> None:
        self._reports: list[ReconciliationReport] = []

    def append(self, report: ReconciliationReport) -> None:
        self._reports.append(report)

    def list_reports(self) -> list[ReconciliationReport]:
        return list(self._reports)

    def get_by_date(self, recon_date: str) -> ReconciliationReport | None:
        for r in self._reports:
            if r.recon_date == recon_date:
                return r
        return None

    def list_breaches(self) -> list[ReconciliationReport]:
        return [r for r in self._reports if r.breach_detected]


# ── Engine ────────────────────────────────────────────────────────────────────


class ReconciliationEngineV2:
    """
    CASS 7.15 daily reconciliation engine.
    Matches ledger entries vs bank statement entries by IBAN.
    Decimal-safe throughout (I-01). Append-only store (I-24).
    """

    def __init__(self, store: ReconStorePort) -> None:
        self._store = store

    def run_daily(
        self,
        recon_date: object,
        ledger_entries: list[dict],
        statement_entries: list[StatementEntry],
    ) -> ReconciliationReport:
        """
        Run daily reconciliation for a given date.
        recon_date: date object or str (YYYY-MM-DD).
        ledger_entries: list of dicts with 'account_iban' and 'amount' (str/Decimal).
        statement_entries: list of StatementEntry.
        """
        date_str = str(recon_date)

        # Build ledger map: IBAN → Decimal amount (I-01)
        ledger_map: dict[str, Decimal] = {}
        for entry in ledger_entries:
            iban = entry["account_iban"]
            amount = Decimal(str(entry["amount"]))
            ledger_map[iban] = ledger_map.get(iban, Decimal("0")) + amount

        # Build statement map: IBAN → Decimal amount (I-01)
        stmt_map: dict[str, Decimal] = {}
        for stmt in statement_entries:
            stmt_map[stmt.account_iban] = (
                stmt_map.get(stmt.account_iban, Decimal("0")) + stmt.amount
            )

        # All IBANs
        all_ibans = set(ledger_map) | set(stmt_map)
        items: list[ReconciliationItem] = []

        for iban in sorted(all_ibans):
            ledger_amt = ledger_map.get(iban, Decimal("0"))
            stmt_amt = stmt_map.get(iban, Decimal("0"))
            discrepancy = abs(ledger_amt - stmt_amt)

            if iban not in ledger_map:
                status = "MISSING_LEDGER"
            elif iban not in stmt_map:
                status = "MISSING_STATEMENT"
            elif discrepancy <= RECON_TOLERANCE_GBP:
                status = "MATCHED"
            else:
                status = "DISCREPANCY"

            item_id = hashlib.sha256(f"{iban}{date_str}".encode()).hexdigest()[:8]
            items.append(
                ReconciliationItem(
                    item_id=item_id,
                    account_iban=iban,
                    ledger_amount=ledger_amt,
                    statement_amount=stmt_amt,
                    discrepancy=discrepancy,
                    recon_date=date_str,
                    status=status,
                )
            )

        total_ledger = sum(ledger_map.values(), Decimal("0"))
        total_stmt = sum(stmt_map.values(), Decimal("0"))
        net_discrepancy = abs(total_ledger - total_stmt)
        breach_detected = any(
            i.status in ("DISCREPANCY", "MISSING_LEDGER", "MISSING_STATEMENT") for i in items
        )

        if breach_detected:
            logger.warning(
                "CASS 7.15 BREACH detected for %s — net discrepancy GBP %s",
                date_str,
                net_discrepancy,
            )

        report_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        report = ReconciliationReport(
            report_id=report_id,
            recon_date=date_str,
            total_ledger_gbp=total_ledger,
            total_statement_gbp=total_stmt,
            net_discrepancy_gbp=net_discrepancy,
            items=tuple(items),
            breach_detected=breach_detected,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._store.append(report)  # I-24: append-only
        return report

    def resolve_breach(self, report_id: str, resolved_by: str) -> HITLProposal:
        """
        L4 HITL — propose a breach resolution. Never auto-resolves (I-27).
        Returns HITLProposal; COMPLIANCE_OFFICER must approve.
        """
        entity_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        return HITLProposal(
            action="resolve_breach",
            entity_id=entity_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=f"Breach resolution requested for report {report_id} by {resolved_by}",
            autonomy_level="L4",
        )
