"""services/risk/risk_metrics_port.py — RiskMetricsPort: governed READ-ONLY risk
metrics CONTRACT (ADR-079, CRO dashboard).

EXPLICIT BOUNDARY: READ ONLY — fetch risk metrics for the CRO dashboard.
This port does NOT change thresholds, approve models, make risk decisions,
or write anything. There are NO mutating / approve / threshold methods on
this port at all.

WHY: ADR-079 defines the CRO risk-oversight agent as the governed surface through
which the Chief Risk Officer accesses aggregate exposure, monitoring counters, and
Consumer Duty signals. The RiskMetricsPort is the CONTRACT boundary the
RiskOversightAgent mask ``scope`` allow-lists (ADR-049 §D1). The read-only
constraint is an invariant: the port has no mutating methods so the agent cannot
accidentally call one.

Governance contract (ADR-049 §D1 — canonical):
  reads: get_aggregate_exposure, get_monitoring_counters,
         get_consumer_duty_signals, get_risk_dashboard

PII / R-SEC (R-SEC-NEW-01, ADR-021):
  All value types carry only aggregated / non-personal data. No method accepts or
  returns raw PII (no customer IDs, names, IBANs, or personal transaction details).
  ``total_gbp`` is the EMI-wide aggregate exposure, not a per-customer balance.

I-01 (CLAUDE.md): monetary fields (``AggregateExposure.total_gbp``) are Decimal,
never float.
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from decimal import Decimal

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class RiskMetricsPortError(Exception):
    """Base error for RiskMetricsPort read failures.

    Adapters raise this (or a subclass) when a risk-data fetch fails.
    RiskOversightAgent catches it, emits one lineage record (executed=False),
    then re-raises — defense-in-depth (ADR-046 / ADR-027). Correlate failures
    via ``AgentDecisionRecord.correlation_id``.
    """


# ---------------------------------------------------------------------------
# Value types (frozen=True — immutable after construction, I-01 Decimal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateExposure:
    """EMI-wide aggregate client-fund exposure snapshot (READ-ONLY).

    ``total_gbp`` is the sum of all safeguarded client funds in GBP-equivalent
    at the time of the snapshot. I-01: Decimal, never float.

    Required fields:
      total_gbp — aggregate exposure in GBP (Decimal).
      as_of     — ISO-8601 date/datetime string of the snapshot.
    """

    total_gbp: Decimal
    as_of: str


@dataclass(frozen=True)
class MonitoringCounters:
    """Operational monitoring counters for the CRO dashboard (READ-ONLY).

    Integer counts only — no raw transaction data or PII.

    Required fields:
      fraud_alerts — open fraud alerts at snapshot time.
      aml_alerts   — open AML alerts at snapshot time.
      as_of        — ISO-8601 date/datetime string of the snapshot.
    """

    fraud_alerts: int
    aml_alerts: int
    as_of: str


@dataclass(frozen=True)
class ConsumerDutySignal:
    """A single Consumer Duty outcome metric signal (READ-ONLY).

    Carries the metric name and its outcome label (e.g., WITHIN_TOLERANCE /
    REQUIRES_REVIEW). No raw customer data or PII.

    Required fields:
      metric  — non-PII metric identifier (e.g., "complaints_rate").
      outcome — outcome label (e.g., "WITHIN_TOLERANCE").
      as_of   — ISO-8601 date/datetime string of the signal.
    """

    metric: str
    outcome: str
    as_of: str


@dataclass(frozen=True)
class RiskDashboard:
    """Aggregated CRO risk dashboard snapshot (READ-ONLY).

    Combines all three risk metric categories into a single response object.
    Intended as the primary read surface for the CRO agent.

    Required fields:
      aggregate    — EMI-wide aggregate exposure (AggregateExposure).
      counters     — monitoring counters (MonitoringCounters).
      consumer_duty — list of Consumer Duty signals (may be empty).
      as_of        — ISO-8601 date/datetime string of the dashboard snapshot.
    """

    aggregate: AggregateExposure
    counters: MonitoringCounters
    consumer_duty: list[ConsumerDutySignal]
    as_of: str


# ---------------------------------------------------------------------------
# Abstract port (READ-ONLY CONTRACT, ADR-079)
# ---------------------------------------------------------------------------


class RiskMetricsPort(abc.ABC):
    """Abstract CONTRACT for governed READ-ONLY risk metrics (ADR-079 CRO mask).

    INVARIANT: Every method on this port is a pure read. There are NO methods
    for approving models, changing thresholds, filing risk decisions, or
    mutating any state. The absence of mutating methods is the primary
    enforcement mechanism for the RiskOversightAgent read-only invariant.

    Conformance rules:
      Read-only (ADR-079 §D1): NO operation mutates state, changes thresholds,
      or moves money. The four reads MUST NOT trigger any state change.

      PII (ADR-021): All entity references are aggregate/non-personal. No method
      returns raw PII or per-customer transaction data.

      I-01: ``total_gbp`` in AggregateExposure is Decimal.
    """

    @abstractmethod
    async def get_aggregate_exposure(self) -> AggregateExposure:
        """Return the EMI-wide aggregate client-fund exposure snapshot (read-only).

        Read-only; MUST NOT trigger any state change. I-01: total_gbp is Decimal.

        Returns:
            AggregateExposure with Decimal total_gbp and an as_of timestamp.

        Raises:
            RiskMetricsPortError: if the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_monitoring_counters(self) -> MonitoringCounters:
        """Return current operational monitoring counters (read-only).

        Read-only; MUST NOT trigger any state change.

        Returns:
            MonitoringCounters with fraud_alerts and aml_alerts integer counts.

        Raises:
            RiskMetricsPortError: if the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_consumer_duty_signals(self) -> list[ConsumerDutySignal]:
        """Return the current Consumer Duty outcome signals (read-only).

        Read-only; MUST NOT trigger any state change.

        Returns:
            A list of ConsumerDutySignal (possibly empty).

        Raises:
            RiskMetricsPortError: if the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_risk_dashboard(self) -> RiskDashboard:
        """Return the full aggregated CRO risk dashboard snapshot (read-only).

        Aggregates get_aggregate_exposure, get_monitoring_counters, and
        get_consumer_duty_signals into a single RiskDashboard. Read-only;
        MUST NOT trigger any state change.

        Returns:
            RiskDashboard combining all three metric categories.

        Raises:
            RiskMetricsPortError: if the read fails.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# InMemory implementation (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryRiskMetricsPort(RiskMetricsPort):
    """Configurable in-memory stub for unit tests.

    Seed data is provided at construction time. Pass ``fail_on_call=True`` to
    make every method raise :class:`RiskMetricsPortError` — exercises the agent
    HALT_PROVIDER_ERROR branch.
    """

    def __init__(
        self,
        *,
        fail_on_call: bool = False,
        exposure: AggregateExposure | None = None,
        counters: MonitoringCounters | None = None,
        signals: list[ConsumerDutySignal] | None = None,
    ) -> None:
        self._fail = fail_on_call
        self._exposure: AggregateExposure = exposure or AggregateExposure(
            total_gbp=Decimal("1_000_000.00"),
            as_of="2026-06-11",
        )
        self._counters: MonitoringCounters = counters or MonitoringCounters(
            fraud_alerts=5,
            aml_alerts=3,
            as_of="2026-06-11",
        )
        self._signals: list[ConsumerDutySignal] = (
            signals
            if signals is not None
            else [
                ConsumerDutySignal(
                    metric="complaints_rate",
                    outcome="WITHIN_TOLERANCE",
                    as_of="2026-06-11",
                )
            ]
        )

    def _check_fail(self) -> None:
        if self._fail:
            raise RiskMetricsPortError("InMemoryRiskMetricsPort configured to fail")

    async def get_aggregate_exposure(self) -> AggregateExposure:
        self._check_fail()
        return self._exposure

    async def get_monitoring_counters(self) -> MonitoringCounters:
        self._check_fail()
        return self._counters

    async def get_consumer_duty_signals(self) -> list[ConsumerDutySignal]:
        self._check_fail()
        return list(self._signals)

    async def get_risk_dashboard(self) -> RiskDashboard:
        self._check_fail()
        return RiskDashboard(
            aggregate=self._exposure,
            counters=self._counters,
            consumer_duty=list(self._signals),
            as_of=self._exposure.as_of,
        )


__all__ = [
    "AggregateExposure",
    "ConsumerDutySignal",
    "InMemoryRiskMetricsPort",
    "MonitoringCounters",
    "RiskDashboard",
    "RiskMetricsPort",
    "RiskMetricsPortError",
]
