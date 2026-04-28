"""
services/recon/recon_engine.py
ReconciliationEngine — FCA CASS 7 daily safeguarding recon (IL-SAF-01).

Compares client fund totals against safeguarding account balances.
Detects discrepancies, flags large values, excludes blocked jurisdictions,
and records immutable audit trail.

I-01: Decimal ONLY for money.
I-02: Blocked jurisdictions excluded from recon.
I-04: Large values (>£50k) flagged for MLRO.
I-24: Immutable audit trail for every reconciliation.
I-27: HITL escalation for shortfalls.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from services.recon.recon_models import (
    BLOCKED_JURISDICTIONS,
    LARGE_VALUE_THRESHOLD,
    RECON_TOLERANCE,
    AccountBalance,
    Discrepancy,
    DiscrepancyType,
    EscalationLevel,
    ReconAuditEntry,
    ReconResult,
    ReconStatus,
)
from services.recon.recon_port import LedgerPort

# ── Audit Port ───────────────────────────────────────────────────────────────


class ReconAuditPort(Protocol):
    """Port for recording immutable recon audit entries (I-24)."""

    def record(self, entry: ReconAuditEntry) -> None: ...


class InMemoryReconAuditPort:
    """In-memory audit trail for tests."""

    def __init__(self) -> None:
        self._entries: list[ReconAuditEntry] = []

    def record(self, entry: ReconAuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[ReconAuditEntry]:
        return list(self._entries)


# ── HITL Escalation ──────────────────────────────────────────────────────────


class HITLEscalation:
    """Represents a HITL escalation for discrepancy resolution (I-27)."""

    def __init__(
        self,
        recon_id: str,
        discrepancy: Discrepancy,
        requires_approval_from: str = "MLRO",
    ) -> None:
        self.recon_id = recon_id
        self.discrepancy = discrepancy
        self.requires_approval_from = requires_approval_from


# ── Reconciliation Engine ────────────────────────────────────────────────────


class ReconciliationEngine:
    """
    FCA CASS 7 daily safeguarding reconciliation engine.

    Compares total client funds against total safeguarding balances.
    Excludes blocked jurisdictions (I-02).
    Flags large values (I-04).
    Records audit trail (I-24).
    Escalates discrepancies via HITL (I-27).
    """

    def __init__(
        self,
        ledger: LedgerPort,
        audit: ReconAuditPort | None = None,
        tolerance: Decimal | None = None,
    ) -> None:
        self._ledger = ledger
        self._audit: ReconAuditPort = audit or InMemoryReconAuditPort()
        self._tolerance = tolerance if tolerance is not None else RECON_TOLERANCE
        self._escalations: list[HITLEscalation] = []

    @property
    def escalations(self) -> list[HITLEscalation]:
        """Return pending HITL escalations."""
        return list(self._escalations)

    def run_daily_recon(self, recon_date: str) -> ReconResult:
        """
        Execute daily reconciliation for the given date.

        Returns ReconResult with status BALANCED or DISCREPANCY.
        Triggers HITL escalation for shortfalls (I-27).
        """
        recon_id = f"recon-{uuid4().hex[:12]}"

        # Fetch balances from ledger port.
        client_balances = self._ledger.get_client_fund_balances(recon_date)
        safeguarding_balances = self._ledger.get_safeguarding_balances(recon_date)

        # I-02: exclude blocked jurisdictions.
        excluded: list[str] = []
        client_balances_filtered: list[AccountBalance] = []
        for bal in client_balances:
            if bal.jurisdiction.upper() in BLOCKED_JURISDICTIONS:
                excluded.append(bal.jurisdiction.upper())
            else:
                client_balances_filtered.append(bal)

        safeguarding_filtered: list[AccountBalance] = []
        for bal in safeguarding_balances:
            if bal.jurisdiction.upper() in BLOCKED_JURISDICTIONS:
                excluded.append(bal.jurisdiction.upper())
            else:
                safeguarding_filtered.append(bal)

        # I-01: sum with Decimal.
        client_total = sum(
            (b.balance for b in client_balances_filtered), Decimal("0")
        )
        safeguarding_total = sum(
            (b.balance for b in safeguarding_filtered), Decimal("0")
        )
        difference = client_total - safeguarding_total

        # I-04: flag large values.
        large_values_flagged = sum(
            1 for b in client_balances_filtered
            if b.balance >= LARGE_VALUE_THRESHOLD
        ) + sum(
            1 for b in safeguarding_filtered
            if b.balance >= LARGE_VALUE_THRESHOLD
        )

        # Detect discrepancies.
        discrepancies: list[Discrepancy] = []
        if abs(difference) > self._tolerance:
            disc_type = (
                DiscrepancyType.SHORTFALL if difference > Decimal("0")
                else DiscrepancyType.SURPLUS
            )
            escalation = (
                EscalationLevel.HITL_MLRO if abs(difference) >= LARGE_VALUE_THRESHOLD
                else EscalationLevel.ALERT
            )
            disc = Discrepancy(
                discrepancy_id=f"disc-{uuid4().hex[:8]}",
                discrepancy_type=disc_type,
                expected=client_total,
                actual=safeguarding_total,
                difference=abs(difference),
                account_id="AGGREGATE",
                description=(
                    f"Daily recon {recon_date}: client funds {client_total} vs "
                    f"safeguarding {safeguarding_total}, difference {difference}"
                ),
                escalation_level=escalation,
            )
            discrepancies.append(disc)

            # I-27: HITL escalation for shortfalls.
            if disc_type == DiscrepancyType.SHORTFALL:
                self._escalations.append(
                    HITLEscalation(
                        recon_id=recon_id,
                        discrepancy=disc,
                        requires_approval_from="MLRO",
                    )
                )

        status = (
            ReconStatus.BALANCED if not discrepancies
            else ReconStatus.DISCREPANCY
        )

        result = ReconResult(
            recon_id=recon_id,
            recon_date=recon_date,
            status=status,
            client_funds_total=client_total,
            safeguarding_total=safeguarding_total,
            difference=difference,
            discrepancies=tuple(discrepancies),
            large_values_flagged=large_values_flagged,
            excluded_jurisdictions=tuple(sorted(set(excluded))),
        )

        # I-24: audit trail.
        self._record_audit(recon_id, result)

        return result

    def _record_audit(self, recon_id: str, result: ReconResult) -> None:
        entry = ReconAuditEntry(
            recon_id=recon_id,
            action="DAILY_RECON",
            status=result.status,
            client_funds_total=result.client_funds_total,
            safeguarding_total=result.safeguarding_total,
            actor="SYSTEM",
            details=(
                f"discrepancies={len(result.discrepancies)}, "
                f"large_values={result.large_values_flagged}, "
                f"excluded={','.join(result.excluded_jurisdictions) or 'none'}"
            ),
        )
        self._audit.record(entry)
