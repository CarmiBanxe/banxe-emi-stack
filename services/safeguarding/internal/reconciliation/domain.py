"""
services/safeguarding/internal/reconciliation/domain.py — Domain model + ports
for the Safeguarding + Reconciliation engine (Sprint S16.4 PREP).

Scope (per IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 §S16.4 + FCA
CASS 15 §15.10):

  - DAILY reconciliation of e-money outstanding (sum of customer balances,
    "internal") vs the safeguarding bank account balance ("external",
    Modulr live API target — Sprint S20.1).
  - Break detection: threshold-based, configurable in both absolute
    minor-units AND relative basis-points, per currency.
  - Every run + every break logged to ClickHouse Guardian via the
    ADR-027 BufferedAuditPort (5-year retention).
  - MLRO notification when break above EMERGENCY threshold (Sprint S20.5
    Telegram MLRO channel).

This module defines pure domain types + Protocol ports. NO I/O, NO live
calls, NO production-bound implementation. Adapter stubs and the
operator-facing runbook live in sibling files (see algorithm.md and
adapters/modulr_safeguarding_stub.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class ReconciliationStatus(str, Enum):
    """Lifecycle states for a single reconciliation run."""

    STARTED = "STARTED"
    INGESTING = "INGESTING"
    DETECTING = "DETECTING"
    AWAITING_HITL = "AWAITING_HITL"  # EMERGENCY-threshold break: requires Central + MLRO co-sign
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ThresholdBreachKind(str, Enum):
    """Which configured threshold(s) a break violated."""

    ABSOLUTE = "ABSOLUTE"  # delta in minor units exceeds absolute threshold
    RELATIVE = "RELATIVE"  # delta in basis points exceeds relative threshold
    BOTH = "BOTH"


@dataclass(frozen=True)
class ReconciliationThreshold:
    """Per-currency break-detection configuration (ValueObject).

    A delta is a break if it exceeds the absolute OR the relative threshold
    (the engine records which kind tripped). EMERGENCY-tier handling lives
    in the algorithm + runbook, not on this VO.
    """

    currency: str
    absolute_minor_units: int  # I-01 invariant: integer minor units, never float
    relative_basis_points: int  # 1 bp = 0.01 % of the larger of the two balances


@dataclass
class ReconciliationBreak:
    """A single ledger ↔ statement mismatch detected within a run."""

    id: str
    run_id: str
    customer_id_hash: str  # sha256[:16] — never store raw customer id
    currency: str
    internal_balance: Decimal  # source of truth: customer-balance store (per I-01)
    external_balance: Decimal  # source of truth: Modulr safeguarding account
    delta_absolute: int  # signed minor units (positive = internal > external)
    delta_relative: int  # signed basis points
    threshold_breach_kind: ThresholdBreachKind
    detected_at: datetime


@dataclass
class ReconciliationRun:
    """One reconciliation cycle — daily by default."""

    id: str
    started_at: datetime
    ended_at: datetime | None
    status: ReconciliationStatus
    total_balance_internal: Decimal  # aggregate across all in-scope currencies, GBP-normalised
    total_balance_external: Decimal  # aggregate across all in-scope currencies, GBP-normalised
    break_count: int
    break_total: Decimal  # absolute sum of |delta| across all breaks, GBP-normalised
    breaks: list[ReconciliationBreak] = field(default_factory=list)
    thresholds: list[ReconciliationThreshold] = field(default_factory=list)


class ReconciliationPort(Protocol):
    """Orchestration port — drives one run end-to-end.

    Concrete adapter lives in a separate module (out of S16.4 PREP scope;
    the algorithm.md sketch documents the operational sequence).
    """

    def start_run(
        self, run_id: str, thresholds: list[ReconciliationThreshold]
    ) -> ReconciliationRun: ...
    def ingest_internal_balances(self, run_id: str) -> ReconciliationRun: ...
    def ingest_external_balances(self, run_id: str) -> ReconciliationRun: ...
    def detect_breaks(self, run_id: str) -> list[ReconciliationBreak]: ...
    def finalize_run(self, run_id: str, status: ReconciliationStatus) -> ReconciliationRun: ...


class SafeguardingExternalPort(Protocol):
    """Read the live safeguarding bank account balance.

    Production adapter target = Modulr live API (Sprint S20.1). The S16.4
    PREP package only ships a stub (modulr_safeguarding_stub.py).
    """

    def fetch_safeguarding_balance(self, account_id: str, currency: str) -> Decimal: ...


class AuditSinkPort(Protocol):
    """Audit emission for the reconciliation engine.

    Production binding wraps ADR-027 BufferedAuditPort (5y ClickHouse
    retention). The PREP package does not bind here — algorithm.md
    documents the event vocabulary (RECON_RUN_STARTED /
    RECON_RUN_COMPLETED / RECON_BREAK_DETECTED).
    """

    def log_run(self, run: ReconciliationRun) -> None: ...
    def log_break(self, run: ReconciliationRun, break_record: ReconciliationBreak) -> None: ...
