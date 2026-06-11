"""services/data_quality/data_quality_port.py — DataQualityPort: governed READ-ONLY
data quality & drift CONTRACT (ADR-080, CTO DataQualityAgent).

EXPLICIT BOUNDARY: READ ONLY — detection and reporting of data-quality and drift
signals only. This port does NOT mutate data, trigger pipeline runs, update models,
or retrain models. There are NO mutate/trigger/retrain methods on this port at all
(I-10: no fake integrations, I-27: no autonomous model updates).

WHY: ADR-080 defines the CTO data-quality agent as the governed surface through
which the Chief Technology Officer accesses drift scores, quality reports, dataset
freshness, and dataset discovery. The DataQualityPort is the CONTRACT boundary the
DataQualityAgent mask ``scope`` allow-lists (ADR-049 §D1). The read-only constraint
is an invariant: the port has no mutating methods so the agent cannot accidentally
call one.

Governance contract (ADR-049 §D1 — canonical):
  reads: get_drift_score, get_quality_report, list_datasets, get_freshness

PII / R-SEC (R-SEC-NEW-01, ADR-021):
  All value types carry only aggregated / non-personal data. No method accepts or
  returns raw PII. Dataset identifiers are opaque handles, not customer references.

I-01 (CLAUDE.md): numeric quality metrics (drift_score, null_rate, schema_conformance)
are Decimal, never float.
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from decimal import Decimal

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class DataQualityPortError(Exception):
    """Base error for DataQualityPort read failures.

    Adapters raise this (or a subclass) when a data-quality fetch fails.
    DataQualityAgent catches it, emits one lineage record (executed=False),
    then re-raises — defense-in-depth (ADR-046 / ADR-027). Correlate failures
    via ``AgentDecisionRecord.correlation_id``.
    """


# ---------------------------------------------------------------------------
# Value types (frozen=True — immutable after construction, I-01 Decimal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftSignal:
    """A single dataset drift signal snapshot (READ-ONLY).

    I-01: drift_score is Decimal, never float.

    Required fields:
      dataset     — dataset identifier (non-PII opaque handle).
      drift_score — drift magnitude as Decimal (range: [0.0, 1.0]).
      as_of       — ISO-8601 date/datetime string of the snapshot.
    """

    dataset: str
    drift_score: Decimal
    as_of: str


@dataclass(frozen=True)
class DataQualityReport:
    """Full data quality report for a dataset (READ-ONLY).

    I-01: all numeric quality metric fields are Decimal, never float.

    Required fields:
      dataset             — dataset identifier (non-PII opaque handle).
      null_rate           — fraction of null values as Decimal [0.0, 1.0].
      schema_conformance  — fraction of schema-conformant records as Decimal [0.0, 1.0].
      freshness_seconds   — integer seconds since last data update.
      drift_score         — drift magnitude as Decimal [0.0, 1.0].
      as_of               — ISO-8601 date/datetime string of the report.
    """

    dataset: str
    null_rate: Decimal
    schema_conformance: Decimal
    freshness_seconds: int
    drift_score: Decimal
    as_of: str


# ---------------------------------------------------------------------------
# Abstract port (READ-ONLY CONTRACT, ADR-080)
# ---------------------------------------------------------------------------


class DataQualityPort(abc.ABC):
    """Abstract CONTRACT for governed READ-ONLY data quality & drift metrics (ADR-080).

    INVARIANT: Every method on this port is a pure read. There are NO methods
    for triggering pipeline runs, retraining models, updating data, or mutating
    any state. The absence of mutating methods is the primary enforcement mechanism
    for the DataQualityAgent read-only invariant (I-27).

    Conformance rules:
      Read-only (ADR-080 §D1): NO operation mutates state, triggers pipelines,
      or retrains models. The four reads MUST NOT trigger any state change.

      I-01: all numeric quality metric fields are Decimal, never float.
    """

    @abstractmethod
    async def get_drift_score(self, dataset: str) -> DriftSignal:
        """Return the current drift signal for a dataset (read-only).

        Read-only; MUST NOT trigger any state change. I-01: drift_score is Decimal.

        Returns:
            DriftSignal with Decimal drift_score and an as_of timestamp.

        Raises:
            DataQualityPortError: if the dataset is unknown or the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_quality_report(self, dataset: str) -> DataQualityReport:
        """Return the full quality report for a dataset (read-only).

        Read-only; MUST NOT trigger any state change. I-01: all numeric fields Decimal.

        Returns:
            DataQualityReport with Decimal quality metrics.

        Raises:
            DataQualityPortError: if the dataset is unknown or the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def list_datasets(self) -> list[str]:
        """Return the list of known dataset identifiers (read-only).

        Read-only; MUST NOT trigger any state change.

        Returns:
            A list of dataset identifier strings (possibly empty).

        Raises:
            DataQualityPortError: if the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_freshness(self, dataset: str) -> int:
        """Return freshness_seconds for a dataset (read-only).

        Read-only; MUST NOT trigger any state change.

        Returns:
            Integer seconds since last data update.

        Raises:
            DataQualityPortError: if the dataset is unknown or the read fails.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# InMemory implementation (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryDataQualityPort(DataQualityPort):
    """Configurable in-memory stub for unit tests.

    Seed data is provided at construction time. Pass ``fail_on_call=True`` to
    make every method raise :class:`DataQualityPortError` — exercises the agent
    HALT_PROVIDER_ERROR branch. Raises DataQualityPortError for unknown datasets.
    """

    def __init__(
        self,
        *,
        fail_on_call: bool = False,
        signals: dict[str, DriftSignal] | None = None,
        reports: dict[str, DataQualityReport] | None = None,
    ) -> None:
        self._fail = fail_on_call
        self._signals: dict[str, DriftSignal] = signals or {
            "payments": DriftSignal(
                dataset="payments",
                drift_score=Decimal("0.05"),
                as_of="2026-06-11",
            ),
            "customers": DriftSignal(
                dataset="customers",
                drift_score=Decimal("0.02"),
                as_of="2026-06-11",
            ),
        }
        self._reports: dict[str, DataQualityReport] = reports or {
            "payments": DataQualityReport(
                dataset="payments",
                null_rate=Decimal("0.01"),
                schema_conformance=Decimal("0.99"),
                freshness_seconds=300,
                drift_score=Decimal("0.05"),
                as_of="2026-06-11",
            ),
            "customers": DataQualityReport(
                dataset="customers",
                null_rate=Decimal("0.00"),
                schema_conformance=Decimal("1.00"),
                freshness_seconds=600,
                drift_score=Decimal("0.02"),
                as_of="2026-06-11",
            ),
        }

    def _check_fail(self) -> None:
        if self._fail:
            raise DataQualityPortError("InMemoryDataQualityPort configured to fail")

    async def get_drift_score(self, dataset: str) -> DriftSignal:
        self._check_fail()
        if dataset not in self._signals:
            raise DataQualityPortError(f"Unknown dataset: {dataset!r}")
        return self._signals[dataset]

    async def get_quality_report(self, dataset: str) -> DataQualityReport:
        self._check_fail()
        if dataset not in self._reports:
            raise DataQualityPortError(f"Unknown dataset: {dataset!r}")
        return self._reports[dataset]

    async def list_datasets(self) -> list[str]:
        self._check_fail()
        return list(self._signals.keys())

    async def get_freshness(self, dataset: str) -> int:
        self._check_fail()
        if dataset not in self._reports:
            raise DataQualityPortError(f"Unknown dataset: {dataset!r}")
        return self._reports[dataset].freshness_seconds


__all__ = [
    "DataQualityPort",
    "DataQualityPortError",
    "DataQualityReport",
    "DriftSignal",
    "InMemoryDataQualityPort",
]
