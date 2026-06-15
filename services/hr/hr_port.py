"""hr_port.py — HRPort: people-operations contract (routine reads/writes + SMF appointment).

ORG-STRUCTURE §2.9 (People / HR) — ``HRAgent`` (L1 Auto; gate **CEO on hiring an SMF
holder**). This port isolates the HR-operations domain so adapters (a real HRIS, an
SM&CR workflow tool) can be swapped without touching agent logic. It is the emi-stack
analogue of ``incident_signal_port.py`` / ``churn_signal_port.py``.

Referenced canon:
  ORG §2.9          HRAgent — routine people-ops L1 Auto; SMF hires gated on CEO
  FCA SM&CR         Appointing/changing an SMF (Senior Management Function) holder can
                    NEVER be autonomous — it requires senior (CEO) sign-off
  ADR-046 §D2       one AgentDecisionRecord per action
  ADR-049 §D2/§D3   mask gate-chain + scope allow-list
  ADR-021 / R-SEC   opaque metadata only — employee_id / role only, never PII or salary

THE ROUTINE / SMF-APPOINTMENT BOUNDARY (enforced by construction)
-----------------------------------------------------------------
This port exposes four capabilities split across two consequence classes:

* :meth:`get_training_status`, :meth:`record_conduct_attestation`  — ROUTINE people-ops.
  Low-consequence, L1 AUTO-eligible: training tracking and conduct-rule attestations.
* :meth:`propose_smf_appointment`  — PREPARE ONLY. Builds an :class:`SMFAppointmentProposal`
  with NO token and applies nothing — it cannot, by itself, appoint anyone.
* :meth:`apply_smf_appointment`  — the ONLY method that commits an SMF appointment, and it
  raises :class:`HRPortError` unless a non-empty CEO authorization token is supplied. An
  SMF holder therefore can never be appointed without a CEO token *at the port layer* —
  defence-in-depth beneath the agent's forced-CEO-step-up governance gate.

READ-ONLY SM&CR HANDLE (no domain mutation)
-------------------------------------------
SMF / role data is read through :class:`SMCRReadHandle` — a narrow read-only Protocol
structurally compatible with ``InMemorySMCRRegistry``
(``services/compliance_automation/smcr_registry.py``). This port does NOT import, own, or
mutate the compliance_automation domain; it only *reads* the current SMF holder when
preparing an appointment. A production adapter would poll a real HRIS / SM&CR tool — that
integration is a LATER sprint (I-10: no fake integrations now).

R-SEC (ADR-021): every value object carries opaque metadata ONLY — an ``employee_id`` /
``role`` / ``candidate_id``, never names, salary, performance data, or any PII. The CEO
authorization token is a port argument only; it is never stored on a value object.
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ConductRuleTier(StrEnum):
    """FCA Conduct-Rule tier an attestation covers (mirrors the SM&CR registry bands).

    TIER_1 is every-staff Individual Conduct Rules; TIER_2 is the Senior-Manager
    Conduct Rules. Attesting either is a ROUTINE L1 op — it is bookkeeping, not an
    appointment, so it never trips the SMF gate.
    """

    TIER_1 = "TIER_1"  # Individual Conduct Rules (all staff)
    TIER_2 = "TIER_2"  # Senior-Manager Conduct Rules (SMFs only)


# ---------------------------------------------------------------------------
# Value objects (R-SEC: opaque metadata only — employee_id / role, never PII/salary)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainingStatus:
    """Read-only training-completion status for one employee/course (opaque handles)."""

    employee_id: str
    course_id: str
    completed: bool
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ConductAttestation:
    """A recorded conduct-rule attestation (routine L1 bookkeeping, no appointment)."""

    employee_id: str
    tier: ConductRuleTier
    attested: bool
    recorded_at: datetime


@dataclass(frozen=True)
class SMFAppointmentProposal:
    """A PREPARED SMF-appointment proposal — prepare only, carries NO token and appoints
    nothing. The ``role`` is the FCA SMF function code (e.g. ``"SMF1"``); ``candidate_id``
    is an opaque person handle. Applying it requires :meth:`HRPort.apply_smf_appointment`
    with a CEO authorization token."""

    proposal_id: str
    role: str
    candidate_id: str
    incumbent_id: str | None = None  # current holder (read via the SM&CR handle), if any
    prepared_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SMFAppointment:
    """An APPLIED SMF appointment — only produced by :meth:`HRPort.apply_smf_appointment`
    after a valid CEO token was supplied. ``authorized`` is always True on a returned
    instance (the no-token path raises before one is built)."""

    proposal_id: str
    role: str
    candidate_id: str
    appointed_at: datetime
    authorized: bool = True


# ---------------------------------------------------------------------------
# Read-only SM&CR handle (Protocol) — reads SMF/role data, never mutates
# ---------------------------------------------------------------------------


class SMCRReadHandle(Protocol):
    """Narrow read-only handle into the SM&CR registry
    (``services/compliance_automation/smcr_registry.py``). Structurally compatible with
    ``InMemorySMCRRegistry``: the HR mask reads the current SMF holder through this seam
    and NEVER mutates the registry — there is intentionally no register/file method here.

    Return type is ``object | None`` to avoid importing compliance_automation domain
    models into this port (loose coupling)."""

    def get_senior_manager(self, person_id: str) -> object | None: ...


# ---------------------------------------------------------------------------
# Error hierarchy (carries correlation_id for the audit trail)
# ---------------------------------------------------------------------------


class HRPortError(Exception):
    """Base for all HR-port errors. Carries ``correlation_id`` so the adapter can write
    an audit row before re-raising."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class EmployeeNotFound(HRPortError):
    """employee_id not present in the HR store."""


class HRSourceUnavailable(HRPortError):
    """The HR source is down or returned a transient error (caller retries)."""


class CEOAuthorizationRequired(HRPortError):
    """An SMF appointment was applied without a CEO authorization token. The port refuses
    to appoint an SMF holder without senior sign-off (SM&CR) — defence-in-depth beneath
    the agent's forced CEO step-up."""


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class HRPort(abc.ABC):
    """Abstract contract for people-operations.

    Boundary: routine HR ops (training status, conduct attestations) are free L1 ops;
    an SMF appointment is split into a token-less :meth:`propose_smf_appointment`
    (prepare only) and a CEO-token-gated :meth:`apply_smf_appointment` (the only commit
    seam, which raises without a token). An SMF holder can never be appointed
    autonomously through this port.
    """

    @abstractmethod
    async def get_training_status(self, employee_id: str, course_id: str) -> TrainingStatus:
        """Return an employee's training-completion status (ROUTINE L1 read).

        Raises:
            EmployeeNotFound: no training record for that employee/course.
            HRSourceUnavailable: the HR source is transiently unavailable.
        """
        ...

    @abstractmethod
    async def record_conduct_attestation(
        self, employee_id: str, tier: ConductRuleTier, *, attested: bool
    ) -> ConductAttestation:
        """Record a conduct-rule attestation (ROUTINE L1 bookkeeping — not an appointment).

        Raises:
            HRSourceUnavailable: the HR source is transiently unavailable.
        """
        ...

    @abstractmethod
    def propose_smf_appointment(
        self, role: str, candidate: str, *, incumbent_id: str | None = None
    ) -> SMFAppointmentProposal:
        """PREPARE an SMF-appointment proposal — prepare only, no token, appoints nothing.

        Returns a token-less :class:`SMFAppointmentProposal`. Applying it is a separate,
        CEO-token-gated step (:meth:`apply_smf_appointment`)."""
        ...

    @abstractmethod
    def apply_smf_appointment(
        self, proposal: SMFAppointmentProposal, ceo_token: str
    ) -> SMFAppointment:
        """COMMIT an SMF appointment — requires a non-empty CEO authorization token.

        Raises:
            CEOAuthorizationRequired: ``ceo_token`` is empty/None — an SMF holder is
                never appointed without senior (CEO) sign-off (SM&CR)."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (unit-test double — I-10: no real HRIS yet)
# ---------------------------------------------------------------------------


class InMemoryHRPort(HRPort):
    """In-memory :class:`HRPort` for unit tests. Holds training/attestation state in
    dicts, records calls for assertions, and exposes a transient-failure switch so the
    agent's provider-error path can be exercised.

    Its :meth:`apply_smf_appointment` mirrors the abstract boundary: it raises
    :class:`CEOAuthorizationRequired` without a token, so a test can prove no SMF holder
    is ever appointed through the port without CEO sign-off."""

    def __init__(self, *, unavailable: HRSourceUnavailable | None = None) -> None:
        self._training: dict[tuple[str, str], TrainingStatus] = {}
        self._unavailable = unavailable
        self.get_training_status_calls: list[tuple[str, str]] = []
        self.conduct_attestation_calls: list[tuple[str, ConductRuleTier, bool]] = []
        self.propose_calls: list[tuple[str, str]] = []
        self.apply_calls: list[tuple[str, str]] = []

    # -- test configuration --------------------------------------------------

    def add_training(
        self,
        employee_id: str,
        course_id: str,
        *,
        completed: bool,
        completed_at: datetime | None = None,
    ) -> TrainingStatus:
        status = TrainingStatus(
            employee_id=employee_id,
            course_id=course_id,
            completed=completed,
            completed_at=completed_at,
        )
        self._training[(employee_id, course_id)] = status
        return status

    def set_unavailable(self, exc: HRSourceUnavailable) -> None:
        self._unavailable = exc

    # -- routine ops (L1) ----------------------------------------------------

    async def get_training_status(self, employee_id: str, course_id: str) -> TrainingStatus:
        self.get_training_status_calls.append((employee_id, course_id))
        if self._unavailable is not None:
            raise self._unavailable
        status = self._training.get((employee_id, course_id))
        if status is None:
            raise EmployeeNotFound(
                f"No training record for {employee_id}/{course_id}",
                correlation_id=employee_id,
            )
        return status

    async def record_conduct_attestation(
        self, employee_id: str, tier: ConductRuleTier, *, attested: bool
    ) -> ConductAttestation:
        self.conduct_attestation_calls.append((employee_id, tier, attested))
        if self._unavailable is not None:
            raise self._unavailable
        return ConductAttestation(
            employee_id=employee_id,
            tier=tier,
            attested=attested,
            recorded_at=datetime.now(UTC),
        )

    # -- SMF appointment (prepare-only / CEO-token-gated commit) --------------

    def propose_smf_appointment(
        self, role: str, candidate: str, *, incumbent_id: str | None = None
    ) -> SMFAppointmentProposal:
        self.propose_calls.append((role, candidate))
        return SMFAppointmentProposal(
            proposal_id=f"SMF-PROP-{role}-{candidate}",
            role=role,
            candidate_id=candidate,
            incumbent_id=incumbent_id,
        )

    def apply_smf_appointment(
        self, proposal: SMFAppointmentProposal, ceo_token: str
    ) -> SMFAppointment:
        if not ceo_token:
            raise CEOAuthorizationRequired(
                "SMF appointment requires a CEO authorization token (SM&CR); refused.",
                correlation_id=proposal.proposal_id,
            )
        self.apply_calls.append((proposal.proposal_id, proposal.candidate_id))
        return SMFAppointment(
            proposal_id=proposal.proposal_id,
            role=proposal.role,
            candidate_id=proposal.candidate_id,
            appointed_at=datetime.now(UTC),
        )


class InMemorySMCRReadHandle:
    """In-memory :class:`SMCRReadHandle` for unit tests — reads SMF holders from a dict
    and records lookups for assertions. Holds ``object`` values so tests are not coupled
    to compliance_automation domain models (any structural stand-in works)."""

    def __init__(self, *, senior_managers: dict[str, object] | None = None) -> None:
        self._sm: dict[str, object] = dict(senior_managers or {})
        self.get_senior_manager_calls: list[str] = []

    def get_senior_manager(self, person_id: str) -> object | None:
        self.get_senior_manager_calls.append(person_id)
        return self._sm.get(person_id)


__all__ = [
    "CEOAuthorizationRequired",
    "ConductAttestation",
    "ConductRuleTier",
    "EmployeeNotFound",
    "HRPort",
    "HRPortError",
    "HRSourceUnavailable",
    "InMemoryHRPort",
    "InMemorySMCRReadHandle",
    "SMCRReadHandle",
    "SMFAppointment",
    "SMFAppointmentProposal",
    "TrainingStatus",
]
