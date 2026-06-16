"""services/churn/churn_signal_port.py — ChurnSignalPort: governed READ-ONLY
at-risk / churn-signal CONTRACT (ORG §2.6.3, IL-188 ChurnPredictionAgent).

EXPLICIT BOUNDARY: READ ONLY — detection and reporting of churn / at-risk signals
only. This port does NOT mutate customer state, trigger retention campaigns, write
to the lifecycle FSM, or train any model. There are NO mutate / trigger / write
methods on this port at all (I-10: no fake integrations, I-27: no autonomous
customer-state changes or retention actions).

WHY: ORG §2.6.3 (Customer Operations) defines ``ChurnPredictionAgent`` (L1 Auto, at-risk
customer alerts) as the governed surface through which Customer Operations reads at-risk
signals. The ChurnSignalPort is the CONTRACT boundary the ChurnPredictionAgent mask
``scope`` allow-lists (ADR-049 §D1). The read-only constraint is an invariant: the port
has no mutating methods, so the agent cannot accidentally call one.

DERIVED FROM THE LIFECYCLE DOMAIN (NOT a new ML model):
The at-risk signals are DERIVED, read-only, from the existing customer-state domain
``services/customer_lifecycle/`` (``CustomerState`` — e.g. DORMANT / SUSPENDED — and the
append-only transition history). :class:`ChurnSignalCode` mirrors those state-derived
signals (DORMANCY, SUSPENSION, INACTIVITY, REACTIVATION_LAPSE). This port is the CONTRACT
boundary only; any production adapter reads the lifecycle domain BEHIND this port and
MUST NOT modify it (a later sprint, like the analytics adapter). This file authors no such
adapter and touches no customer_lifecycle logic — it ships the contract + an in-memory
double for unit tests.

Governance contract (ADR-049 §D1 — canonical):
  reads: get_at_risk_customers, get_churn_signals

PII / R-SEC (R-SEC-NEW-01, ADR-021):
  All value types carry only opaque handles (``customer_id`` / ``cohort``) and aggregate
  signals. No method accepts or returns raw PII (no name / email / IBAN / address).
  ``customer_id`` is an opaque handle, never a personal reference.

I-01 (CLAUDE.md): every numeric field (risk_score, signal weight) is Decimal, never float.
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

# Opaque customer / cohort handles. NEVER raw PII (no name / email / IBAN / address).
CustomerId = str
Cohort = str

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RiskBand(StrEnum):
    """Coarse at-risk band for a customer (derived from the aggregate risk_score)."""

    LOW = "LOW"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"


class ChurnSignalCode(StrEnum):
    """A state-derived churn signal. Mirrors the customer_lifecycle ``CustomerState``
    signals the production adapter reads BEHIND this port (read-only derivation):

      DORMANCY           — customer is in ``CustomerState.DORMANT``.
      SUSPENSION         — customer is in ``CustomerState.SUSPENDED``.
      INACTIVITY         — approaching the dormancy inactivity window (no transition).
      REACTIVATION_LAPSE — reactivated then lapsed back toward dormancy.
    """

    DORMANCY = "DORMANCY"
    SUSPENSION = "SUSPENSION"
    INACTIVITY = "INACTIVITY"
    REACTIVATION_LAPSE = "REACTIVATION_LAPSE"


# ---------------------------------------------------------------------------
# Value types (frozen=True — immutable after construction, I-01 Decimal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChurnSignal:
    """A single derived churn signal contributing to a customer's risk (READ-ONLY).

    I-01: ``weight`` is Decimal, never float.

    Required fields:
      code   — the state-derived signal code.
      weight — contribution of this signal to the aggregate risk_score, Decimal [0.0, 1.0].

    Optional fields:
      detail — short opaque, non-PII note (e.g. "dormant 120d"); defaults to "".
    """

    code: ChurnSignalCode
    weight: Decimal
    detail: str = ""


@dataclass(frozen=True)
class AtRiskCustomer:
    """An at-risk customer entry in an at-risk scan result (READ-ONLY).

    I-01: ``risk_score`` is Decimal, never float. R-SEC: ``customer_id`` / ``cohort``
    are opaque handles only — never raw PII.

    Required fields:
      customer_id — opaque customer handle (no raw PII).
      cohort      — opaque cohort label the customer belongs to (no raw PII).
      risk_score  — aggregate churn risk as Decimal [0.0, 1.0].
      band        — coarse risk band derived from risk_score.
    """

    customer_id: CustomerId
    cohort: Cohort
    risk_score: Decimal
    band: RiskBand


@dataclass(frozen=True)
class ChurnSignalSet:
    """The full set of derived churn signals for one customer (READ-ONLY).

    I-01: ``risk_score`` and every signal weight are Decimal, never float.

    Required fields:
      customer_id — opaque customer handle (no raw PII).
      cohort      — opaque cohort label (no raw PII).
      risk_score  — aggregate churn risk as Decimal [0.0, 1.0].
      band        — coarse risk band derived from risk_score.

    Optional fields:
      signals     — the individual derived signals; defaults to empty.
    """

    customer_id: CustomerId
    cohort: Cohort
    risk_score: Decimal
    band: RiskBand
    signals: tuple[ChurnSignal, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ChurnSignalPortError(Exception):
    """Base error for ChurnSignalPort read failures.

    Adapters raise this (or a subclass) when a churn-signal fetch fails.
    ChurnPredictionAgent catches it, emits one lineage record (executed=False),
    then re-raises — defense-in-depth (ADR-046 / ADR-027).
    """


class CustomerNotFound(ChurnSignalPortError):
    """The requested ``customer_id`` has no derived churn signals (unknown handle)."""


# ---------------------------------------------------------------------------
# Abstract port (READ-ONLY CONTRACT)
# ---------------------------------------------------------------------------


class ChurnSignalPort(abc.ABC):
    """Abstract CONTRACT for governed READ-ONLY at-risk / churn-signal reads (ORG §2.6.3).

    INVARIANT: Every method on this port is a pure read. There are NO methods for
    triggering retention campaigns, writing customer state, or mutating any state.
    The absence of mutating methods is the primary enforcement mechanism for the
    ChurnPredictionAgent read-only invariant (I-27).

    Conformance rules:
      Read-only: NO operation mutates state, triggers retention, or changes the
      customer lifecycle. The two reads MUST NOT trigger any state change.

      I-01: every numeric field (risk_score, weight) is Decimal, never float.

      R-SEC: only opaque handles (customer_id / cohort) cross this boundary — no raw PII.
    """

    @abstractmethod
    async def get_at_risk_customers(self, threshold: Decimal) -> list[AtRiskCustomer]:
        """Return the at-risk customers whose risk_score >= ``threshold`` (read-only).

        Read-only; MUST NOT trigger any state change or retention action. I-01:
        ``threshold`` and every returned risk_score are Decimal.

        Args:
            threshold: minimum aggregate risk_score to include, Decimal [0.0, 1.0].

        Returns:
            A list of AtRiskCustomer (possibly empty), highest risk first.

        Raises:
            ChurnSignalPortError: if the threshold is out of range or the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_churn_signals(self, customer_id: CustomerId) -> ChurnSignalSet:
        """Return the derived churn signals for one customer (read-only).

        Read-only; MUST NOT trigger any state change or retention action.

        Args:
            customer_id: opaque customer handle to read signals for (no raw PII).

        Returns:
            The ChurnSignalSet for the customer.

        Raises:
            CustomerNotFound: ``customer_id`` has no derived signals (unknown handle).
            ChurnSignalPortError: if the read otherwise fails.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# InMemory implementation (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryChurnSignalPort(ChurnSignalPort):
    """Configurable in-memory stub for unit tests.

    Seed data is provided at construction time. Pass ``fail_on_call=True`` to make
    every method raise :class:`ChurnSignalPortError` — exercises the agent
    HALT_PROVIDER_ERROR branch. Raises :class:`CustomerNotFound` for unknown customers
    and :class:`ChurnSignalPortError` for an out-of-range threshold. READ-ONLY: there is
    no method to mutate state or trigger retention.
    """

    def __init__(
        self,
        *,
        fail_on_call: bool = False,
        signals: Mapping[CustomerId, ChurnSignalSet] | None = None,
    ) -> None:
        self._fail = fail_on_call
        self._signals: dict[CustomerId, ChurnSignalSet] = dict(
            signals
            if signals is not None
            else {
                "cust-1001": ChurnSignalSet(
                    customer_id="cust-1001",
                    cohort="retail-eu",
                    risk_score=Decimal("0.82"),
                    band=RiskBand.HIGH,
                    signals=(
                        ChurnSignal(
                            code=ChurnSignalCode.DORMANCY,
                            weight=Decimal("0.60"),
                            detail="dormant 120d",
                        ),
                        ChurnSignal(
                            code=ChurnSignalCode.INACTIVITY,
                            weight=Decimal("0.22"),
                            detail="no transition 90d",
                        ),
                    ),
                ),
                "cust-1002": ChurnSignalSet(
                    customer_id="cust-1002",
                    cohort="retail-eu",
                    risk_score=Decimal("0.30"),
                    band=RiskBand.ELEVATED,
                    signals=(
                        ChurnSignal(
                            code=ChurnSignalCode.REACTIVATION_LAPSE,
                            weight=Decimal("0.30"),
                            detail="re-lapsed after reactivate",
                        ),
                    ),
                ),
            }
        )

    def _check_fail(self) -> None:
        if self._fail:
            raise ChurnSignalPortError("InMemoryChurnSignalPort configured to fail")

    async def get_at_risk_customers(self, threshold: Decimal) -> list[AtRiskCustomer]:
        self._check_fail()
        if not Decimal("0") <= threshold <= Decimal("1"):
            raise ChurnSignalPortError(f"threshold out of range: {threshold!r}")
        at_risk = [
            AtRiskCustomer(
                customer_id=s.customer_id,
                cohort=s.cohort,
                risk_score=s.risk_score,
                band=s.band,
            )
            for s in self._signals.values()
            if s.risk_score >= threshold
        ]
        return sorted(at_risk, key=lambda c: c.risk_score, reverse=True)

    async def get_churn_signals(self, customer_id: CustomerId) -> ChurnSignalSet:
        self._check_fail()
        if customer_id not in self._signals:
            raise CustomerNotFound(f"Unknown customer: {customer_id!r}")
        return self._signals[customer_id]


__all__ = [
    "AtRiskCustomer",
    "ChurnSignal",
    "ChurnSignalCode",
    "ChurnSignalPort",
    "ChurnSignalPortError",
    "ChurnSignalSet",
    "Cohort",
    "CustomerId",
    "CustomerNotFound",
    "InMemoryChurnSignalPort",
    "RiskBand",
]
