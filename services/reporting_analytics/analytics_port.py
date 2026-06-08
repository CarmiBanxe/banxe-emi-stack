"""analytics_port.py — AnalyticsPort: governed read-only analytics CONTRACT (C7).

ADR-054 Analytics / Reporting client-facing mask (C7) — the second extended-catalogue
entry (extends ADR-049 via ADR-053). This file is the CONTRACT port that the
Analytics (C7) mask `scope` allow-lists.

Referenced ADRs / specs:
  ADR-054  Analytics / Reporting (C7) mask. Defines C7 as a low-consequence
           read/reporting surface: AUTO-biased reads, REVIEW only for large /
           sensitive export (data-egress), NO biometric step-up (no money
           movement), PII overlay + data-egress gate. AnalyticsPort is the
           CONTRACT boundary the mask `scope` allow-lists (ADR-054 §D1).
  ADR-053  Client-facing mask catalogue extensibility; the mask <-> domain-agent
           governance boundary (every mask scopes a real hexagonal CONTRACT port,
           never a client surface directly).
  ADR-049  Intent-layer client-facing agent masks (the §D2 gate chain, §D3 mask
           fields, §D4 thresholds). C7 reuses these unchanged; §D4 critical
           money-movement step-up does NOT apply here (no value-bearing action).
  ADR-046  Decision Lineage Schema — one AgentDecisionRecord per masked action.
  ADR-047  AI Cost Governance Policy — per-request / per-window cost caps on
           potentially compute-heavy aggregation.
  ADR-016  AI-plane PII/AML routing — PII overlay on any client-fund / personal
           data surfaced by a read or summary.

WHY THIS FILE EXISTS
--------------------
ADR-054 adds the Analytics / Reporting (C7) mask but is SPECIFICATION / CONTRACT
ONLY — it authors no port. A mask may only scope operations on a real hexagonal
CONTRACT port (ADR-053 D1: "no mask may scope a capability that has no port").
AnalyticsPort is that boundary object: the Analytics (C7) mask `scope`
allow-lists exactly the governed read/report operations defined here, and nothing
outside this port is reachable through the mask.

AnalyticsPort exposes ONLY the ADR-054 §D1 allow-list — the governed
client-surface read/report operations:
  reads      : get_spending_summary, get_portfolio_view, get_report,
               list_available_reports
  data-egress: request_export   (REVIEW only for large / sensitive datasets)

GOVERNANCE BOUNDARY (ADR-054 D2 — canonical)
--------------------------------------------
AnalyticsPort is the boundary where governance (in front) meets domain
implementation (behind). The mask-governed client-facing AnalyticsAgent sits IN
FRONT of this port and calls it through the full ADR-049 §D2 chain; the existing
domain service-agent `services/reporting_analytics/analytics_agent.py` (and its
`data_aggregator` / `report_builder` / `export_engine` / `scheduled_reports` /
`dashboard_metrics` collaborators) sits BEHIND this port as the ADAPTER,
untouched. A client intent MUST NOT reach the domain agent directly — that would
be an ungoverned read/PII/egress path (no lineage, no cost-cap, no PII overlay,
no export gate).

This file authors NO adapter and touches NO existing reporting_analytics logic
(ADR-054 §E: contract / specification only; the adapter wiring is a later sprint).

READ-ONLY — NO MUTATION, NO MONEY MOVEMENT
------------------------------------------
ADR-054 §D1: C7 operations are read / aggregate / report only. NO method on this
port mutates state, moves money, or writes to client balances. Every operation is
side-effect-free with respect to funds and domain state: it reads and aggregates,
or (request_export) emits a downloadable artefact derived from reads. The only
non-AUTO posture is the data-egress gate on request_export — that gate governs
*egress of data*, never a value-bearing action, so the ADR-049 §D4 biometric
step-up does not apply.

PII — OPAQUE entity_id ONLY, NO RAW PII
---------------------------------------
ADR-016 PII overlay: every entity reference crossing this contract is an opaque
`entity_id` (a customer/entity handle), never raw PII. No method accepts or
returns a name, email, IBAN, address, or other raw personal data. Any adapter
fulfilling this port MUST keep client-fund / personal data behind the PII overlay
and redact it from every exportable artefact (the export_engine PII redaction
already does this behind the port).

CONFORMANCE TEST SUITE
-----------------------
Conformance tests (IDs 1-5) per CONTRACT SPEC enforce the behavioural contract
documented on each method and exception class below.

  1. get_spending_summary(known)  -> SpendingSummary (Decimal totals); read-only,
                                      no mutation, no audit-of-mutation row.
  2. get_portfolio_view(known)    -> PortfolioView; read-only.
  3. get_report(known)            -> ReportView; unknown -> ReportNotFound.
  4. list_available_reports(eid)  -> list[ReportDescriptor]; read-only.
  5. request_export(small)        -> ExportResult; export over the configured
                                      data-egress materiality -> ExportTooLarge
                                      (REVIEW gate); PII/compliance failure ->
                                      ComplianceBlock.

FUTURE WORK (out of scope here)
--------------------------------
- The AnalyticsPort adapter wiring the existing reporting_analytics domain agent
  behind this port (ADR-054 D3; later sprint).
- The mask-governed AnalyticsAgent in services/agents/ (ADR-054 D3).
- The Analytics mask catalogue entry values (cost_cap, export materiality
  thresholds) as config-as-data (ADR-054 D1/D4; CLAUDE.md §10).
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Opaque customer/entity handle. NEVER raw PII (no name/email/IBAN/address).
EntityId = str
ReportId = str

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SpendPeriod(StrEnum):
    """Window over which a spending summary is aggregated."""

    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    YEAR = "YEAR"
    CUSTOM = "CUSTOM"


class ReportFormat(StrEnum):
    """Output format of a report / export artefact."""

    JSON = "JSON"
    CSV = "CSV"
    PDF = "PDF"
    EXCEL = "EXCEL"


class ExportStatus(StrEnum):
    """Lifecycle status of a data-egress export request (ADR-054 data-egress gate).

    Transitions relevant to the mask allow-list:
      PENDING_REVIEW --(REVIEW approved)--> READY
      PENDING_REVIEW --(REVIEW rejected / blocked)--> REJECTED
      small / in-cap export                       --> READY (AUTO)
    """

    READY = "READY"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Value objects  (frozen=True — immutable after construction)
#
# READ-ONLY: none of these carry mutating intent. PII: entity references are the
# opaque EntityId only — no raw personal data crosses this boundary.
# I-01 / money rule (CLAUDE.md): monetary amounts are Decimal, never float.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpendingSummary:
    """Aggregated spend for an entity over a period (read-only).

    I-01 / money rule: `total` and every `by_category` amount are Decimal,
    never float.

    Required fields:
      entity_id   — opaque entity the summary is for (no raw PII).
      period      — the window aggregated over.
      total       — total spend across all categories (Decimal).
      by_category — per-category spend, mapping category name -> amount (Decimal);
                    defaults to empty.
      currency    — ISO-4217 currency of the amounts.
    """

    entity_id: EntityId
    period: SpendPeriod
    total: Decimal
    currency: str
    by_category: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioPosition:
    """A single holding within a portfolio view (read-only, Decimal amounts)."""

    asset: str
    quantity: Decimal
    market_value: Decimal
    currency: str


@dataclass(frozen=True)
class PortfolioView:
    """Snapshot of an entity's portfolio (read-only aggregate).

    I-01 / money rule: `total_value` and every position amount are Decimal.

    Required fields:
      entity_id   — opaque entity the view is for (no raw PII).
      total_value — total portfolio market value (Decimal).
      currency    — ISO-4217 currency of total_value.
      positions   — the individual holdings; defaults to empty.
    """

    entity_id: EntityId
    total_value: Decimal
    currency: str
    positions: list[PortfolioPosition] = field(default_factory=list)


@dataclass(frozen=True)
class ReportView:
    """A rendered (or render-ready) report returned by get_report (read-only).

    Required fields:
      report_id  — opaque canonical report identifier.
      entity_id  — opaque entity the report belongs to (no raw PII).
      title      — display title (non-PII).
      format     — the report's output format.
      rows       — tabular report payload, already PII-redacted by the adapter;
                   defaults to empty.
    """

    report_id: ReportId
    entity_id: EntityId
    title: str
    format: ReportFormat
    rows: list[Mapping[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ReportDescriptor:
    """A listing entry describing a report available to an entity (read-only).

    Required fields:
      report_id   — opaque report identifier.
      title       — display title (non-PII).
      format      — output format the report renders to.
      description — human-readable description (non-PII); defaults to "".
    """

    report_id: ReportId
    title: str
    format: ReportFormat
    description: str = ""


@dataclass(frozen=True)
class ExportRequest:
    """Request to export a report / dataset (ADR-054 data-egress gate).

    request_export is the only non-AUTO operation: export of a large / sensitive
    dataset crossing the configured materiality steps to REVIEW. There is NO money
    movement, so NO biometric step-up applies — the gate is data-egress, not a
    value-bearing action.

    Required fields:
      entity_id      — opaque entity the export is for (no raw PII).
      report_id      — opaque report to export.
      format         — desired export format.
      actor          — identity initiating the export (for audit / lineage).
      correlation_id — links the export to its originating business flow.

    Optional fields:
      include_pii    — whether the caller requests un-redacted PII; defaults to
                       False. True forces the PII / compliance overlay and may
                       raise ComplianceBlock.
    """

    entity_id: EntityId
    report_id: ReportId
    format: ReportFormat
    actor: str
    correlation_id: str
    include_pii: bool = False


@dataclass(frozen=True)
class ExportResult:
    """Result of a request_export call (read-derived artefact, no mutation).

    I-12 (export integrity): `file_hash` is the SHA-256 of the exported artefact,
    computed by the adapter (export_engine). `size_bytes` is what the data-egress
    materiality gate measures against.

    Required fields:
      report_id   — opaque report that was exported.
      format      — format of the produced artefact.
      status      — READY (AUTO / approved) or PENDING_REVIEW (data-egress gate).
      size_bytes  — size of the artefact, in bytes.

    Optional fields:
      file_hash    — SHA-256 of the artefact (I-12); None while PENDING_REVIEW.
      pii_redacted — whether PII was redacted from the artefact; defaults to True.
    """

    report_id: ReportId
    format: ReportFormat
    status: ExportStatus
    size_bytes: int
    file_hash: str | None = None
    pii_redacted: bool = True


# ---------------------------------------------------------------------------
# Error hierarchy
# (all carry correlation_id; the adapter persists exactly one audit row per
#  failed operation before re-raising — ADR-027 / ADR-046)
# ---------------------------------------------------------------------------


class AnalyticsPortError(Exception):
    """Base for all AnalyticsPort errors.

    Every subclass carries correlation_id so the adapter can write exactly one
    audit row per failed operation before re-raising. Keyword-only argument forces
    callers to supply the identifier explicitly (mirrors CardPortError).
    """

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class ReportNotFound(AnalyticsPortError):
    """report_id does not resolve to any report (conformance test 3).

    Caller action: surface to user; do not retry with the same id.
    """


class ExportTooLarge(AnalyticsPortError):
    """The export exceeds the configured data-egress materiality (ADR-054 gate).

    The request crosses the "large / sensitive export" threshold and must step to
    REVIEW rather than complete AUTO (conformance test 5). Caller action: route
    the export through the REVIEW / approval path; do not retry AUTO as-is.
    """


class ComplianceBlock(AnalyticsPortError):
    """A PII / compliance gate (ADR-016) blocked the operation.

    Raised when an export requests un-redacted PII the overlay forbids, or a read
    fails the PII overlay. Caller action: do not retry; escalate to the
    compliance / MLRO path. The adapter MUST log the blocked attempt.
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class AnalyticsPort(abc.ABC):
    """Abstract CONTRACT for governed read-only analytics ops (ADR-054 C7 mask).

    This port is the ADR-054 D2 boundary object: the Analytics (C7) mask `scope`
    allow-lists exactly the operations below; the mask-governed AnalyticsAgent
    calls them through the ADR-049 §D2 chain; the existing reporting_analytics
    domain agent is the adapter behind them. Nothing outside this surface is
    client-reachable.

    Conformance rules (enforced by the conformance suite, CONTRACT SPEC):

    Read-only (ADR-054 §D1):
      NO operation mutates state, moves money, or writes to client balances. The
      reads (get_spending_summary, get_portfolio_view, get_report,
      list_available_reports) MUST NOT trigger any state change. request_export
      emits a downloadable artefact derived from reads — it does not mutate funds
      or domain state.

    PII (ADR-016):
      Every entity reference is the opaque entity_id; no method accepts or returns
      raw PII. Exported artefacts are PII-redacted by the adapter unless the
      compliance overlay explicitly authorises otherwise.

    Data-egress gate (ADR-054):
      request_export of a large / sensitive dataset steps to REVIEW
      (ExportTooLarge / ExportStatus.PENDING_REVIEW). There is NO biometric
      step-up — the gate is data-egress, not a value-bearing action.

    Cost / lineage (ADR-047 / ADR-046):
      Potentially compute-heavy aggregation is bounded by the mask cost-cap; the
      mask layer emits one AgentDecisionRecord per action on every exit path.
    """

    @abstractmethod
    async def get_spending_summary(
        self,
        entity_id: EntityId,
        period: SpendPeriod,
    ) -> SpendingSummary:
        """Return an aggregated spending summary for an entity (read-only).

        Read-only; MUST NOT trigger any state change or move money
        (conformance test 1). Passes the ADR-016 PII overlay; amounts are Decimal.

        Args:
            entity_id: opaque entity to summarise (no raw PII).
            period:    the window to aggregate over.

        Returns:
            SpendingSummary with Decimal total and per-category breakdown.

        Raises:
            ComplianceBlock: the PII overlay blocked the read.
        """
        ...

    @abstractmethod
    async def get_portfolio_view(self, entity_id: EntityId) -> PortfolioView:
        """Return a snapshot of an entity's portfolio (read-only).

        Read-only; MUST NOT trigger any state change (conformance test 2).
        Monetary values are Decimal.

        Args:
            entity_id: opaque entity whose portfolio to view (no raw PII).

        Returns:
            PortfolioView with Decimal total_value and positions.

        Raises:
            ComplianceBlock: the PII overlay blocked the read.
        """
        ...

    @abstractmethod
    async def get_report(self, report_id: ReportId) -> ReportView:
        """Return a single rendered report (read-only).

        Read-only; MUST NOT trigger any state change. Report rows are
        PII-redacted by the adapter (conformance test 3).

        Args:
            report_id: opaque report to read.

        Returns:
            ReportView for the report.

        Raises:
            ReportNotFound: report_id unknown (conformance test 3).
        """
        ...

    @abstractmethod
    async def list_available_reports(
        self,
        entity_id: EntityId,
    ) -> list[ReportDescriptor]:
        """List the reports available to an entity (read-only).

        Read-only; MUST NOT trigger any state change (conformance test 4).

        Args:
            entity_id: opaque entity whose available reports to list (no raw PII).

        Returns:
            A list of ReportDescriptor (possibly empty).
        """
        ...

    @abstractmethod
    async def request_export(self, request: ExportRequest) -> ExportResult:
        """Request an export of a report / dataset (ADR-054 data-egress gate).

        This is the only non-AUTO operation. An export within the configured
        materiality completes AUTO (ExportStatus.READY); an export of a large /
        sensitive dataset steps to REVIEW (conformance test 5). NO money movement
        occurs and NO biometric step-up applies — the gate is data-egress only.
        The produced artefact is PII-redacted unless the compliance overlay
        authorises otherwise.

        Args:
            request: immutable export request including correlation_id and the
                     desired format.

        Returns:
            ExportResult — READY with a file_hash, or PENDING_REVIEW pending the
            data-egress REVIEW.

        Raises:
            ReportNotFound:  request.report_id unknown.
            ExportTooLarge:  export crosses the data-egress materiality (REVIEW).
            ComplianceBlock: the PII / compliance overlay blocked the export.
        """
        ...
