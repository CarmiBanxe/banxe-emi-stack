"""services/lead_scoring/lead_signal_port.py — LeadSignalPort: governed READ-ONLY
behavioral lead-signal CONTRACT (ORG-STRUCTURE §2.8 Sales, IL-190 LeadScoringAgent).

EXPLICIT BOUNDARY: READ ONLY — behavioral lead scoring and reporting only (signup →
active). This port does NOT mutate state, contact / outreach leads, write to any CRM /
referral record, enrol a lead in a nurture sequence, or train any model. There are NO
mutate / contact / outreach / write methods on this port at all (I-10: no fake
integrations, I-27: no autonomous customer-state changes or outreach actions).

WHY: ORG-STRUCTURE §2.8 (Front Office) / §2.8.2 (Marketing & Growth) defines
``LeadScoringAgent`` (Sales, L1 Auto, "Behavioral scoring (signup → active)") as the
governed surface through which Sales reads a lead's behavioral propensity score. The
LeadSignalPort is the CONTRACT boundary the LeadScoringAgent mask ``scope`` allow-lists
(ADR-049 §D1). The read-only constraint is an invariant: the port has no mutating methods,
so the agent cannot accidentally call one.

A CONTRACT ABSTRACTION (NOT a real ML model / ClickHouse integration):
The behavioral lead score is a read-only abstraction. ORG §2.8.2 names ClickHouse +
scikit-learn as the production stack; that real adapter (reading the behavioral-event
stream from ClickHouse and serving a scikit-learn propensity model BEHIND this port) is a
LATER sprint (I-10: no fake integrations now — exactly like the analytics / churn
adapters). There is NO existing lead / sales / marketing domain to derive from (``referral/``
and ``crm/`` exist but are NOT lead scoring), so this is a full BUILD: this file ships the
CONTRACT + an in-memory double for unit tests only, and authors no production adapter.

Governance contract (ADR-049 §D1 — canonical):
  reads: get_active_leads, get_lead_score

PII / R-SEC (R-SEC-NEW-01, ADR-021):
  All value types carry only opaque handles (``lead_id`` / ``cohort``) and aggregate
  signals. No method accepts or returns raw PII (no name / email / IBAN / address) or raw
  behavioral events. ``lead_id`` is an opaque handle, never a personal reference.

I-01 (CLAUDE.md): every numeric field (score, signal weight, threshold) is Decimal, never
float.
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

# Opaque lead / cohort handles. NEVER raw PII (no name / email / IBAN / address).
LeadId = str
Cohort = str

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class LeadScoreBand(StrEnum):
    """Coarse propensity band for a lead (derived from the aggregate behavioral score)."""

    COLD = "COLD"
    WARM = "WARM"
    HOT = "HOT"


class LeadStage(StrEnum):
    """A lead's position in the signup → active funnel (read-only, behavioral).

    SIGNUP     — account created, no further activation behavior yet.
    ONBOARDING — progressing through onboarding (profile / KYC steps).
    ACTIVATED  — completed activation milestones; not yet a sustained active user.
    ACTIVE     — sustained active engagement (the funnel goal).
    """

    SIGNUP = "SIGNUP"
    ONBOARDING = "ONBOARDING"
    ACTIVATED = "ACTIVATED"
    ACTIVE = "ACTIVE"


class LeadSignalCode(StrEnum):
    """A behavioral signal contributing to a lead's propensity score (read-only).

    These are aggregate behavioral indicators a production adapter would derive from the
    behavioral-event stream (ClickHouse) BEHIND this port — never raw events here:

      SIGNUP_COMPLETED    — completed the signup flow.
      PROFILE_COMPLETION  — profile / KYC fields completed.
      ONBOARDING_PROGRESS — advanced through onboarding steps.
      FEATURE_ENGAGEMENT  — engaged with core product features.
      SESSION_RECENCY     — recent active sessions (recency / frequency).
    """

    SIGNUP_COMPLETED = "SIGNUP_COMPLETED"
    PROFILE_COMPLETION = "PROFILE_COMPLETION"
    ONBOARDING_PROGRESS = "ONBOARDING_PROGRESS"
    FEATURE_ENGAGEMENT = "FEATURE_ENGAGEMENT"
    SESSION_RECENCY = "SESSION_RECENCY"


# ---------------------------------------------------------------------------
# Value types (frozen=True — immutable after construction, I-01 Decimal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeadSignal:
    """A single behavioral signal contributing to a lead's propensity score (READ-ONLY).

    I-01: ``weight`` is Decimal, never float.

    Required fields:
      code   — the behavioral signal code.
      weight — contribution of this signal to the aggregate score, Decimal [0.0, 1.0].

    Optional fields:
      detail — short opaque, non-PII note (e.g. "3 sessions/7d"); defaults to "".
    """

    code: LeadSignalCode
    weight: Decimal
    detail: str = ""


@dataclass(frozen=True)
class ScoredLead:
    """A scored lead entry in an active-leads scan result (READ-ONLY).

    I-01: ``score`` is Decimal, never float. R-SEC: ``lead_id`` / ``cohort`` are opaque
    handles only — never raw PII.

    Required fields:
      lead_id — opaque lead handle (no raw PII).
      cohort  — opaque cohort label the lead belongs to (no raw PII).
      score   — aggregate behavioral propensity as Decimal [0.0, 1.0].
      band    — coarse propensity band derived from score.
      stage   — the lead's stage in the signup → active funnel.
    """

    lead_id: LeadId
    cohort: Cohort
    score: Decimal
    band: LeadScoreBand
    stage: LeadStage


@dataclass(frozen=True)
class LeadScore:
    """The full behavioral propensity score for one lead (READ-ONLY).

    I-01: ``score`` and every signal weight are Decimal, never float.

    Required fields:
      lead_id — opaque lead handle (no raw PII).
      cohort  — opaque cohort label (no raw PII).
      score   — aggregate behavioral propensity as Decimal [0.0, 1.0].
      band    — coarse propensity band derived from score.
      stage   — the lead's stage in the signup → active funnel.

    Optional fields:
      signals — the individual behavioral signals; defaults to empty.
    """

    lead_id: LeadId
    cohort: Cohort
    score: Decimal
    band: LeadScoreBand
    stage: LeadStage
    signals: tuple[LeadSignal, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class LeadSignalPortError(Exception):
    """Base error for LeadSignalPort read failures.

    Adapters raise this (or a subclass) when a lead-signal fetch fails. LeadScoringAgent
    catches it, emits one lineage record (executed=False), then re-raises — defense-in-depth
    (ADR-046 / ADR-027).
    """


class LeadNotFound(LeadSignalPortError):
    """The requested ``lead_id`` has no behavioral score (unknown handle)."""


# ---------------------------------------------------------------------------
# Abstract port (READ-ONLY CONTRACT)
# ---------------------------------------------------------------------------


class LeadSignalPort(abc.ABC):
    """Abstract CONTRACT for governed READ-ONLY behavioral lead-signal reads (ORG §2.8).

    INVARIANT: Every method on this port is a pure read. There are NO methods for contacting
    / outreaching leads, enrolling in a nurture sequence, writing CRM / referral state, or
    mutating any state. The absence of mutating methods is the primary enforcement mechanism
    for the LeadScoringAgent read-only invariant (I-27).

    Conformance rules:
      Read-only: NO operation mutates state, contacts a lead, or triggers outreach. The two
      reads MUST NOT trigger any state change.

      I-01: every numeric field (score, weight, threshold) is Decimal, never float.

      R-SEC: only opaque handles (lead_id / cohort) cross this boundary — no raw PII, no raw
      behavioral events.
    """

    @abstractmethod
    async def get_active_leads(self, threshold: Decimal) -> list[ScoredLead]:
        """Return the leads whose behavioral score >= ``threshold`` (read-only).

        Read-only; MUST NOT trigger any state change, contact, or outreach. I-01:
        ``threshold`` and every returned score are Decimal.

        Args:
            threshold: minimum aggregate propensity score to include, Decimal [0.0, 1.0].

        Returns:
            A list of ScoredLead (possibly empty), highest score first.

        Raises:
            LeadSignalPortError: if the threshold is out of range or the read fails.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def get_lead_score(self, lead_id: LeadId) -> LeadScore:
        """Return the behavioral propensity score for one lead (read-only).

        Read-only; MUST NOT trigger any state change, contact, or outreach.

        Args:
            lead_id: opaque lead handle to score (no raw PII).

        Returns:
            The LeadScore for the lead.

        Raises:
            LeadNotFound: ``lead_id`` has no behavioral score (unknown handle).
            LeadSignalPortError: if the read otherwise fails.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# InMemory implementation (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryLeadSignalPort(LeadSignalPort):
    """Configurable in-memory stub for unit tests.

    Seed data is provided at construction time. Pass ``fail_on_call=True`` to make every
    method raise :class:`LeadSignalPortError` — exercises the agent HALT_PROVIDER_ERROR
    branch. Raises :class:`LeadNotFound` for unknown leads and :class:`LeadSignalPortError`
    for an out-of-range threshold. READ-ONLY: there is no method to mutate state, contact a
    lead, or trigger outreach.
    """

    def __init__(
        self,
        *,
        fail_on_call: bool = False,
        scores: Mapping[LeadId, LeadScore] | None = None,
    ) -> None:
        self._fail = fail_on_call
        self._scores: dict[LeadId, LeadScore] = dict(
            scores
            if scores is not None
            else {
                "lead-1001": LeadScore(
                    lead_id="lead-1001",
                    cohort="organic-eu",
                    score=Decimal("0.88"),
                    band=LeadScoreBand.HOT,
                    stage=LeadStage.ACTIVATED,
                    signals=(
                        LeadSignal(
                            code=LeadSignalCode.FEATURE_ENGAGEMENT,
                            weight=Decimal("0.55"),
                            detail="core features used",
                        ),
                        LeadSignal(
                            code=LeadSignalCode.SESSION_RECENCY,
                            weight=Decimal("0.30"),
                            detail="5 sessions/7d",
                        ),
                    ),
                ),
                "lead-1002": LeadScore(
                    lead_id="lead-1002",
                    cohort="organic-eu",
                    score=Decimal("0.34"),
                    band=LeadScoreBand.WARM,
                    stage=LeadStage.ONBOARDING,
                    signals=(
                        LeadSignal(
                            code=LeadSignalCode.ONBOARDING_PROGRESS,
                            weight=Decimal("0.34"),
                            detail="2/5 onboarding steps",
                        ),
                    ),
                ),
            }
        )

    def _check_fail(self) -> None:
        if self._fail:
            raise LeadSignalPortError("InMemoryLeadSignalPort configured to fail")

    async def get_active_leads(self, threshold: Decimal) -> list[ScoredLead]:
        self._check_fail()
        if not Decimal("0") <= threshold <= Decimal("1"):
            raise LeadSignalPortError(f"threshold out of range: {threshold!r}")
        active = [
            ScoredLead(
                lead_id=s.lead_id,
                cohort=s.cohort,
                score=s.score,
                band=s.band,
                stage=s.stage,
            )
            for s in self._scores.values()
            if s.score >= threshold
        ]
        return sorted(active, key=lambda lead: lead.score, reverse=True)

    async def get_lead_score(self, lead_id: LeadId) -> LeadScore:
        self._check_fail()
        if lead_id not in self._scores:
            raise LeadNotFound(f"Unknown lead: {lead_id!r}")
        return self._scores[lead_id]


__all__ = [
    "Cohort",
    "InMemoryLeadSignalPort",
    "LeadId",
    "LeadNotFound",
    "LeadScore",
    "LeadScoreBand",
    "LeadSignal",
    "LeadSignalCode",
    "LeadSignalPort",
    "LeadSignalPortError",
    "LeadStage",
    "ScoredLead",
]
