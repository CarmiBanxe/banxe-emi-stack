"""ml_signal_port.py — MLSignalPort: governed ML-pipeline CONTRACT (I-27 dual sign-off).

ORG-STRUCTURE §2.7.1 Data & ML Engineering — ``MLPipelineAgent`` (L3, gate **CRO + CTO**).
This file is the CONTRACT port that the MLPipeline mask `scope` allow-lists. It is the
**LAST** agent of the org chart and the FIRST whose gated surface carries a *dual* human
sign-off (CRO **and** CTO), the strictest mandatory-step-up invariant in the catalogue.

Referenced ADRs / specs / invariants:
  I-27     "No autonomous model updates. All changes require CRO sign-off" (ORG §2.7.1 line
           258), STRENGTHENED here to the gate column **CRO + CTO**: the agent may ONLY
           PROPOSE retraining / threshold changes; it can NEVER apply a model update
           autonomously. Applying requires DUAL human sign-off — a valid CRO token AND a
           valid CTO token. Missing either → the update is NOT applied.
  ADR-049  Intent-layer agent masks (§D2 gate chain, §D3 mask fields, §D4 thresholds). The
           MLPipeline mask reuses these; the §D4 critical step-up is realised here as the
           dual CRO+CTO sign-off on ``apply_model_update``.
  ADR-046  Decision Lineage Schema — one AgentDecisionRecord per masked action.
  ADR-047  AI Cost Governance Policy — per-request / per-window cost caps.
  ADR-021  R-SEC: only opaque handles (``model_id`` / ``proposal_id``) cross this contract —
           NEVER training data, model weights, hyper-parameters, datasets, or PII, and NEVER
           the CRO/CTO sign-off tokens on a returned value.

WHY THIS FILE EXISTS
--------------------
ORG §2.7.1 lists ``MLPipelineAgent`` but is SPECIFICATION ONLY — it authors no port. A mask
may only scope operations on a real hexagonal CONTRACT port (ADR-053 D1). MLSignalPort is
that boundary object: the MLPipeline mask `scope` allow-lists exactly the governed
read / propose / apply operations defined here, and nothing outside this port is reachable
through the mask.

READ-ONLY SIGNAL SOURCES (NOT modified, NOT owned)
--------------------------------------------------
The drift / retraining-need signals are *derived* read-only from the existing CI-governance
and experiment domains (``services/ci_governance/*`` drift_detector / drift_metrics_exporter,
``services/experiment_copilot/*``, ``services/reasoning_bank/*``). This port is the governance
CONTRACT that fronts those read-only signals; it does NOT modify, mutate, or own those
domains. There is NO real ML training framework (I-10) — the ``InMemoryMLSignalPort`` is an
in-memory handle for tests only; a real adapter wiring the live signal sources behind this
port is later-sprint work.

PROPOSE FREE; APPLY NEVER AUTONOMOUS (the dual-gate boundary)
------------------------------------------------------------
  reads   : get_drift_signals   — read-only drift / retraining-need signals.
  propose : propose_retraining  — prepare a RetrainingProposal ONLY. No token, applies
                                  NOTHING; a proposal is a recommendation, never a change.
  apply   : apply_model_update  — the ONLY commit seam. Requires BOTH a CRO token AND a CTO
                                  token; with either missing it raises ``DualSignOffRequired``
                                  and applies NOTHING (defence-in-depth behind the mask gate).

R-SEC (ADR-021)
---------------
Every identifier crossing this contract is the opaque ``model_id`` / ``proposal_id`` handle.
No method accepts or returns training data, weights, hyper-parameters, datasets, or PII. The
CRO/CTO sign-off tokens are routed straight into ``apply_model_update`` and are NEVER returned
on a result object.

CONFORMANCE TEST SUITE
-----------------------
  1. get_drift_signals(known)        -> list[DriftSignal]; read-only; unknown -> ModelNotFound.
  2. propose_retraining(known)       -> RetrainingProposal; no token; applies nothing;
                                        unknown -> ModelNotFound.
  3. apply_model_update(both tokens) -> ModelUpdateResult(applied=True); the update commits.
  4. apply_model_update(missing CRO OR CTO OR both) -> DualSignOffRequired; NOTHING applied.
  5. transient source failure on any op -> MLSignalSourceUnavailable.
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Opaque model identifier. NEVER training data / weights / hyper-parameters / PII.
ModelId = str
# Opaque retraining-proposal identifier. NEVER raw model internals.
ProposalId = str

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DriftSeverity(StrEnum):
    """Severity of a detected drift signal (read-only; derived from CI-governance)."""

    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RetrainingUrgency(StrEnum):
    """Urgency a retraining proposal recommends (a recommendation only — never a change)."""

    ROUTINE = "ROUTINE"
    ELEVATED = "ELEVATED"
    URGENT = "URGENT"


# ---------------------------------------------------------------------------
# Value objects  (frozen=True — immutable after construction)
#
# READ / PROPOSE / APPLY only. R-SEC (ADR-021): identifiers are the opaque
# ModelId / ProposalId only; no training data, weights, hyper-parameters, datasets,
# or PII crosses this contract, and no sign-off token rides a returned value.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftSignal:
    """A read-only drift / retraining-need signal for a model (derived, never mutating).

    R-SEC: carries the opaque ``model_id`` and a non-sensitive ``metric_summary`` string
    only — never the underlying feature data, predictions, or PII.

    Required fields:
      model_id       — opaque model the signal is about (no raw internals/PII).
      drift_detected — whether drift was detected for the model.
      severity       — the DriftSeverity of the signal.
      metric_summary — a short non-sensitive summary string (no raw data/PII).
    """

    model_id: ModelId
    drift_detected: bool
    severity: DriftSeverity
    metric_summary: str


@dataclass(frozen=True)
class RetrainingProposal:
    """A proposal to retrain / re-threshold a model (a recommendation ONLY).

    A proposal applies NOTHING — it is the agent's only autonomous output (I-27). Committing
    it requires the dual CRO+CTO sign-off on ``apply_model_update``.

    R-SEC: carries opaque handles and a non-sensitive rationale only — never training data,
    weights, or PII.

    Required fields:
      proposal_id    — opaque proposal identifier.
      model_id       — opaque model the proposal targets.
      urgency        — the RetrainingUrgency recommended.
      rationale      — a short non-sensitive justification string (no raw data/PII).
    """

    proposal_id: ProposalId
    model_id: ModelId
    urgency: RetrainingUrgency
    rationale: str


@dataclass(frozen=True)
class ModelUpdateResult:
    """Result of a committed ``apply_model_update`` (only reachable with dual sign-off).

    R-SEC: carries opaque handles only — NEVER the CRO/CTO tokens, training data, or weights.

    Required fields:
      proposal_id  — opaque proposal that was applied.
      model_id     — opaque model that was updated.
      applied      — True when the update committed (only path that returns this object).
      version_ref  — opaque handle of the new model version (no raw weights).
    """

    proposal_id: ProposalId
    model_id: ModelId
    applied: bool
    version_ref: str


# ---------------------------------------------------------------------------
# Error hierarchy
# (all carry correlation_id; the adapter persists exactly one audit row per
#  failed operation before re-raising — ADR-027 / ADR-046)
# ---------------------------------------------------------------------------


class MLSignalPortError(Exception):
    """Base for all MLSignalPort errors.

    Every subclass carries correlation_id so the adapter can write exactly one audit row per
    failed operation before re-raising. Keyword-only argument forces callers to supply the
    identifier explicitly (mirrors HRPortError / CardPortError / StatementPortError).
    """

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class ModelNotFound(MLSignalPortError):
    """model_id does not resolve to any known model (conformance tests 1/2).

    Caller action: surface to user; do not retry with the same id.
    """


class DualSignOffRequired(MLSignalPortError):
    """Apply was attempted without BOTH a CRO token AND a CTO token (I-27, conformance test 4).

    Defence-in-depth behind the mask's dual-sign-off gate: the port itself refuses to apply a
    model update unless both human sign-off tokens are present, so NOTHING is applied. Caller
    action: route through the CRO + CTO dual-sign-off path; do not retry the autonomous apply.
    """


class MLSignalSourceUnavailable(MLSignalPortError):
    """A read-only signal source (CI-governance / experiment domains) was unavailable.

    Transient (conformance test 5). Caller action: the mask emits one lineage record
    (executed=False) and re-raises (HALT_PROVIDER_ERROR); retry later.
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class MLSignalPort(abc.ABC):
    """Abstract CONTRACT for governed ML-pipeline operations (ORG §2.7.1, I-27).

    This port is the boundary object: the MLPipeline mask `scope` allow-lists exactly the
    operations below; the mask-governed MLPipelineAgent calls them through the ADR-049 §D2
    chain; a later adapter fronts the read-only signal sources behind them.

    Conformance rules (CONTRACT SPEC):

    Read / propose / apply (I-27):
      get_drift_signals reads; propose_retraining prepares a RetrainingProposal and applies
      NOTHING; apply_model_update is the ONLY commit seam and is NEVER autonomous — it requires
      a valid CRO token AND a valid CTO token, and applies nothing if either is missing.

    R-SEC (ADR-021):
      Every identifier is the opaque model_id / proposal_id; no method accepts or returns
      training data, weights, hyper-parameters, datasets, or PII; the sign-off tokens are
      never returned on a result object.
    """

    @abstractmethod
    async def get_drift_signals(self, model_id: ModelId) -> list[DriftSignal]:
        """Return read-only drift / retraining-need signals for a model.

        Read-only; MUST NOT trigger any state change, retraining, or model update
        (conformance test 1). Signals are derived from the CI-governance / experiment domains.

        Args:
            model_id: opaque model to read signals for (no raw internals/PII).

        Returns:
            A list of DriftSignal (possibly empty).

        Raises:
            ModelNotFound:              model_id unknown (conformance test 1).
            MLSignalSourceUnavailable:  a read-only signal source was unavailable.
        """
        ...

    @abstractmethod
    async def propose_retraining(self, model_id: ModelId) -> RetrainingProposal:
        """Prepare a retraining / re-threshold proposal for a model (a recommendation ONLY).

        Applies NOTHING and requires no token (conformance test 2): a proposal is the agent's
        autonomous output, never a change. Committing it requires the dual CRO+CTO sign-off on
        ``apply_model_update``.

        Args:
            model_id: opaque model to propose retraining for (no raw internals/PII).

        Returns:
            A RetrainingProposal carrying opaque handles and a non-sensitive rationale.

        Raises:
            ModelNotFound:              model_id unknown (conformance test 2).
            MLSignalSourceUnavailable:  a read-only signal source was unavailable.
        """
        ...

    @abstractmethod
    async def apply_model_update(
        self,
        proposal: RetrainingProposal,
        cro_token: str,
        cto_token: str,
    ) -> ModelUpdateResult:
        """Commit a model update from a proposal — the ONLY commit seam (I-27, NEVER autonomous).

        Requires BOTH a valid CRO token AND a valid CTO token. With either missing (empty /
        falsy), the update is NOT applied and ``DualSignOffRequired`` is raised — defence-in-depth
        behind the mask's dual-sign-off gate (conformance tests 3/4).

        R-SEC: the cro_token / cto_token are routed in here ONLY and are NEVER returned on the
        ModelUpdateResult or persisted on any record.

        Args:
            proposal:  the RetrainingProposal to commit (opaque handles only).
            cro_token: the CRO human sign-off token (required, non-empty).
            cto_token: the CTO human sign-off token (required, non-empty).

        Returns:
            ModelUpdateResult(applied=True) with an opaque new-version handle.

        Raises:
            DualSignOffRequired:        the CRO and/or CTO token was missing (conformance test 4).
            ModelNotFound:              the proposal's model_id is unknown.
            MLSignalSourceUnavailable:  the signal / model store was unavailable.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (tests only — I-10: no real ML training framework)
# ---------------------------------------------------------------------------


@dataclass
class InMemoryMLSignalPort(MLSignalPort):
    """In-memory MLSignalPort double (I-10: no real training framework).

    Seeds a set of known model ids with canned drift signals; ``apply_model_update`` enforces
    the dual CRO+CTO sign-off as defence-in-depth and records the proposals it applied. A
    ``fail_with`` switch lets a test exercise the transient-source-failure path.
    """

    signals: dict[ModelId, list[DriftSignal]] = field(default_factory=dict)
    fail_with: MLSignalPortError | None = None
    applied: list[ModelUpdateResult] = field(default_factory=list)
    _proposal_seq: int = 0

    def _guard_source(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def _require_known(self, model_id: ModelId, *, correlation_id: str) -> None:
        if model_id not in self.signals:
            raise ModelNotFound(f"unknown model_id: {model_id}", correlation_id=correlation_id)

    async def get_drift_signals(self, model_id: ModelId) -> list[DriftSignal]:
        self._guard_source()
        self._require_known(model_id, correlation_id=f"drift:{model_id}")
        return list(self.signals[model_id])

    async def propose_retraining(self, model_id: ModelId) -> RetrainingProposal:
        self._guard_source()
        self._require_known(model_id, correlation_id=f"propose:{model_id}")
        signals = self.signals[model_id]
        worst = max((s.severity for s in signals), default=DriftSeverity.NONE)
        urgency = {
            DriftSeverity.CRITICAL: RetrainingUrgency.URGENT,
            DriftSeverity.HIGH: RetrainingUrgency.URGENT,
            DriftSeverity.MODERATE: RetrainingUrgency.ELEVATED,
        }.get(worst, RetrainingUrgency.ROUTINE)
        self._proposal_seq += 1
        return RetrainingProposal(
            proposal_id=f"prop-{model_id}-{self._proposal_seq}",
            model_id=model_id,
            urgency=urgency,
            rationale=f"drift severity {worst.value} on {model_id}; retraining proposed",
        )

    async def apply_model_update(
        self,
        proposal: RetrainingProposal,
        cro_token: str,
        cto_token: str,
    ) -> ModelUpdateResult:
        self._guard_source()
        # I-27 defence-in-depth: refuse to apply without BOTH human sign-off tokens.
        if not cro_token or not cto_token:
            raise DualSignOffRequired(
                "apply_model_update requires BOTH a CRO token AND a CTO token",
                correlation_id=f"apply:{proposal.proposal_id}",
            )
        self._require_known(proposal.model_id, correlation_id=f"apply:{proposal.proposal_id}")
        result = ModelUpdateResult(
            proposal_id=proposal.proposal_id,
            model_id=proposal.model_id,
            applied=True,
            version_ref=f"{proposal.model_id}@v{len(self.applied) + 1}",
        )
        self.applied.append(result)
        return result


__all__ = [
    "DriftSeverity",
    "DriftSignal",
    "DualSignOffRequired",
    "InMemoryMLSignalPort",
    "MLSignalPort",
    "MLSignalPortError",
    "MLSignalSourceUnavailable",
    "ModelId",
    "ModelNotFound",
    "ModelUpdateResult",
    "ProposalId",
    "RetrainingProposal",
    "RetrainingUrgency",
]
