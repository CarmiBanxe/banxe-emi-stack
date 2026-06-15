"""incident_signal_port.py — IncidentSignalPort: read-only security-incident triage contract.

ORG-STRUCTURE §2.7.4 (Security & Compliance) — ``IncidentResponseAgent`` (L2; gate
**CTO + CEO for CRITICAL**). This port isolates the incident-triage domain from any
single signal source so adapters can be swapped without touching agent logic. It is
the emi-stack analogue of ``fraud_port.py`` / ``campaign_port.py``.

Referenced canon:
  ORG §2.7.4        Security incident triage — AI may triage/classify, NEVER auto-close
  FCA SYSC 8.1      Security incident CRITICAL → CEO notified within 2h
  ADR-049 §D2/§D3   mask gate-chain + scope allow-list
  ADR-021 / R-SEC   opaque metadata only — never raw security data or recipient PII

THE READ + CLASSIFY BOUNDARY (enforced by construction)
-------------------------------------------------------
This port exposes EXACTLY three capabilities — :meth:`get_incidents`,
:meth:`get_incident` (reads) and :meth:`classify_severity` (a pure read-only triage
helper). It deliberately offers **no** close / resolve / suppress operation: an
``IncidentResponseAgent`` therefore *cannot* auto-close or suppress a security
incident through this port. Closure of a CRITICAL incident is a human (CTO + CEO)
decision recorded outside this read seam (forced step-up at the agent's governance
layer). This is defence-in-depth: the boundary is structural, not merely policy.

SIGNAL DERIVATION (read-only, no domain mutation)
-------------------------------------------------
Incident signals are DERIVED read-only from the existing observability
(``services/observability``), device-fingerprint (``services/device_fingerprint``)
and ATO-prevention (``services/ato_prevention``) sources — see :class:`IncidentSource`.
This port does NOT import, own, or mutate those domains; a production adapter would
poll them (and a real SIEM/pager) — that integration is a LATER sprint (I-10: no fake
integrations now). This module ships the contract + an in-memory double for unit
tests only.

R-SEC (ADR-021): :class:`IncidentSignal` carries opaque metadata ONLY — an
``incident_id``, its derived ``severity`` / ``source`` / composite ``signal_score`` —
never raw security payloads, log lines, credentials, or recipient PII.
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class IncidentSeverity(StrEnum):
    """Triage severity for a security incident (FCA SYSC 8.1 escalation bands).

    CRITICAL is the regulated band: it can NEVER be auto-closed by the agent and
    forces a step-up to CTO + CEO with a ≤2h notification SLA.
    """

    LOW = "LOW"  # score < 40 — informational, AUTO-triageable
    MEDIUM = "MEDIUM"  # score 40-69 — standard L2 triage
    HIGH = "HIGH"  # score 70-84 — elevated; HITL-biased triage
    CRITICAL = "CRITICAL"  # score >= 85 — mandatory CTO+CEO step-up, never auto-closed


class IncidentStatus(StrEnum):
    """Lifecycle status of a derived incident signal (read-only to the agent)."""

    OPEN = "open"
    TRIAGED = "triaged"
    ESCALATED = "escalated"
    CLOSED = "closed"


class IncidentSource(StrEnum):
    """The read-only signal source an incident was DERIVED from (never mutated)."""

    COMPLIANCE_MONITOR = "observability.compliance_monitor"
    HEALTH_AGGREGATOR = "observability.health_aggregator"
    METRICS_COLLECTOR = "observability.metrics_collector"
    ANOMALY_DETECTOR = "device_fingerprint.anomaly_detector"
    ATO_ENGINE = "ato_prevention.ato_engine"
    VELOCITY_CHECKER = "ato_prevention.velocity_checker"


# Score → severity thresholds (mirrors the fraud_port band convention).
_SEVERITY_BANDS: tuple[tuple[int, IncidentSeverity], ...] = (
    (85, IncidentSeverity.CRITICAL),
    (70, IncidentSeverity.HIGH),
    (40, IncidentSeverity.MEDIUM),
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncidentSignal:
    """A read-only security-incident signal derived from a source.

    R-SEC: opaque metadata only — ``incident_id`` / ``severity`` / ``source`` /
    ``signal_score`` are loggable; no raw security data or PII is ever carried here.
    """

    incident_id: str
    severity: IncidentSeverity
    source: IncidentSource
    signal_score: int  # 0-100 composite triage score (opaque)
    status: IncidentStatus
    detected_at: datetime


# ---------------------------------------------------------------------------
# Error hierarchy (all carry correlation_id for the audit trail)
# ---------------------------------------------------------------------------


class IncidentSignalPortError(Exception):
    """Base for all incident-signal-port errors. Carries ``correlation_id`` so the
    adapter can write an audit row before re-raising."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class IncidentNotFound(IncidentSignalPortError):
    """incident_id not present in the signal store."""


class SignalSourceUnavailable(IncidentSignalPortError):
    """A signal source is down or returned a transient error (caller retries)."""


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class IncidentSignalPort(abc.ABC):
    """Abstract contract for read-only security-incident triage.

    Boundary: READ + classify only. There is intentionally NO close / resolve /
    suppress method — auto-closure is impossible through this seam by construction.
    """

    @abstractmethod
    async def get_incidents(
        self, severity: IncidentSeverity | None = None
    ) -> tuple[IncidentSignal, ...]:
        """Return derived incident signals, optionally filtered by ``severity``
        (``None`` returns all). Read-only; safe to poll.

        Raises:
            SignalSourceUnavailable: a derivation source is transiently unavailable.
        """
        ...

    @abstractmethod
    async def get_incident(self, incident_id: str) -> IncidentSignal:
        """Return a single derived incident signal by id (read-only).

        Raises:
            IncidentNotFound: no signal with that ``incident_id``.
            SignalSourceUnavailable: a derivation source is transiently unavailable.
        """
        ...

    @abstractmethod
    def classify_severity(self, signal_score: int) -> IncidentSeverity:
        """Pure read-only triage helper: map a 0-100 composite signal score to a
        :class:`IncidentSeverity` band. No I/O, no mutation — never closes anything."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (unit-test double — I-10: no real SIEM/pager yet)
# ---------------------------------------------------------------------------


class InMemoryIncidentSignalPort(IncidentSignalPort):
    """In-memory :class:`IncidentSignalPort` for unit tests. Holds derived signals in
    a dict and classifies by score band. Records reads for assertions and exposes a
    transient-failure switch so the agent's provider-error path can be exercised.

    It has NO close/suppress method — mirroring the abstract boundary so a test can
    prove the agent never auto-closes a CRITICAL incident through the port."""

    def __init__(self, *, unavailable: SignalSourceUnavailable | None = None) -> None:
        self._incidents: dict[str, IncidentSignal] = {}
        self._unavailable = unavailable
        self.get_incidents_calls: list[IncidentSeverity | None] = []
        self.get_incident_calls: list[str] = []
        self.classify_calls: list[int] = []

    # -- test configuration --------------------------------------------------

    def add_incident(
        self,
        incident_id: str,
        *,
        signal_score: int,
        source: IncidentSource = IncidentSource.COMPLIANCE_MONITOR,
        status: IncidentStatus = IncidentStatus.OPEN,
        detected_at: datetime | None = None,
        severity: IncidentSeverity | None = None,
    ) -> IncidentSignal:
        signal = IncidentSignal(
            incident_id=incident_id,
            severity=severity or self.classify_severity(signal_score),
            source=source,
            signal_score=signal_score,
            status=status,
            detected_at=detected_at or datetime(2026, 6, 12, tzinfo=None),
        )
        self._incidents[incident_id] = signal
        # classify_severity is a derivation helper — exclude its bookkeeping from the
        # caller-facing classify spy so add_incident does not pollute call assertions.
        self.classify_calls.clear()
        return signal

    def set_unavailable(self, exc: SignalSourceUnavailable) -> None:
        self._unavailable = exc

    # -- port API ------------------------------------------------------------

    async def get_incidents(
        self, severity: IncidentSeverity | None = None
    ) -> tuple[IncidentSignal, ...]:
        self.get_incidents_calls.append(severity)
        if self._unavailable is not None:
            raise self._unavailable
        signals = tuple(self._incidents.values())
        if severity is not None:
            signals = tuple(s for s in signals if s.severity is severity)
        return signals

    async def get_incident(self, incident_id: str) -> IncidentSignal:
        self.get_incident_calls.append(incident_id)
        if self._unavailable is not None:
            raise self._unavailable
        signal = self._incidents.get(incident_id)
        if signal is None:
            raise IncidentNotFound(
                f"No incident signal for id: {incident_id}", correlation_id=incident_id
            )
        return signal

    def classify_severity(self, signal_score: int) -> IncidentSeverity:
        self.classify_calls.append(signal_score)
        for floor, severity in _SEVERITY_BANDS:
            if signal_score >= floor:
                return severity
        return IncidentSeverity.LOW


__all__ = [
    "InMemoryIncidentSignalPort",
    "IncidentNotFound",
    "IncidentSeverity",
    "IncidentSignal",
    "IncidentSignalPort",
    "IncidentSignalPortError",
    "IncidentSource",
    "IncidentStatus",
    "SignalSourceUnavailable",
]
