"""Tests for the MLPipeline mask agent (services/agents/ml_pipeline_agent.py).

Covers every MLPipeline-mask path in the §D2 gate-chain order (ORG §2.7.1, I-27):
the AUTO read path (get_drift_signals) and its below-AUTO re-check halt; the AUTO propose
path (propose_retraining) with the downstream-sign-off signal on its outcome; the I-27
DUAL CRO+CTO sign-off on apply_model_update — the four invariant cases (no tokens / CRO only /
CTO only / both) proving the update is NEVER applied without BOTH human tokens and that the
port is never called when either is missing; the config-floor invariant (a permissive mask
cannot waive the dual sign-off); compliance BLOCK + CRO escalation; cost-cap breach
(per-request and per-window); BLOCK on low confidence; out-of-scope refusal (autonomous apply
refused); unresolved process_ref; the provider-error emit-and-reraise; invalid confidence →
ValueError; the R-SEC no-token-in-lineage guarantee; and the lineage-per-action obligation
(ADR-046). The port and the recorder are fakes — the agent is exercised as pure governance
logic with no live infra or ML framework.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.ml_pipeline_agent import (
    AgentDecisionRecord,
    ApplyModelUpdateIntent,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    DriftSignalIntent,
    MLPipelineAgent,
    MLPipelineMask,
    ProcessRef,
    ProposeRetrainingIntent,
    RequestCost,
)
from services.ml_pipeline.ml_signal_port import (
    DriftSeverity,
    DriftSignal,
    DualSignOffRequired,
    MLSignalPort,
    MLSignalSourceUnavailable,
    ModelUpdateResult,
    RetrainingProposal,
    RetrainingUrgency,
)

_CRO_TOKEN = "cro-signoff-opaque-token"
_CTO_TOKEN = "cto-signoff-opaque-token"
_MODEL = "fraud_v3"

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeMLSignalPort(MLSignalPort):
    """In-test MLSignalPort double. Records calls; returns canned signals/results or raises a
    configured error so the agent's governance logic is exercised with no live ML framework.
    apply_model_update records the tokens it received so a test can assert the port is NEVER
    reached without both human sign-offs."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.drift_calls: list[str] = []
        self.propose_calls: list[str] = []
        self.apply_calls: list[tuple[str, str, str]] = []

    async def get_drift_signals(self, model_id: str) -> list[DriftSignal]:
        self.drift_calls.append(model_id)
        if self._raises is not None:
            raise self._raises
        return [
            DriftSignal(
                model_id=model_id,
                drift_detected=True,
                severity=DriftSeverity.HIGH,
                metric_summary="psi 0.4",
            )
        ]

    async def propose_retraining(self, model_id: str) -> RetrainingProposal:
        self.propose_calls.append(model_id)
        if self._raises is not None:
            raise self._raises
        return RetrainingProposal(
            proposal_id=f"prop-{model_id}-1",
            model_id=model_id,
            urgency=RetrainingUrgency.URGENT,
            rationale="drift high",
        )

    async def apply_model_update(
        self,
        proposal: RetrainingProposal,
        cro_token: str,
        cto_token: str,
    ) -> ModelUpdateResult:
        self.apply_calls.append((proposal.proposal_id, cro_token, cto_token))
        if self._raises is not None:
            raise self._raises
        return ModelUpdateResult(
            proposal_id=proposal.proposal_id,
            model_id=proposal.model_id,
            applied=True,
            version_ref=f"{proposal.model_id}@v1",
        )


def make_mask(**overrides) -> MLPipelineMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return MLPipelineMask(**base)


def make_agent(*, mask: MLPipelineMask | None = None, raises: Exception | None = None):
    port = FakeMLSignalPort(raises=raises)
    recorder = FakeRecorder()
    agent = MLPipelineAgent(
        ml_signal_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=CostWindow(window_ref="ml:test"),
    )
    return agent, port, recorder


def _process() -> ProcessRef:
    return ProcessRef(process_id="proc-ml", version="v1")


def _cost(tokens: int = 100, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def drift_intent(confidence: float = 0.97, **overrides) -> DriftSignalIntent:
    base = {
        "intent_text": "show me drift on fraud_v3",
        "process_ref": _process(),
        "model_id": _MODEL,
        "correlation_id": "corr-1",
        "confidence_score": confidence,
        "request_cost": _cost(),
    }
    base.update(overrides)
    return DriftSignalIntent(**base)


def propose_intent(confidence: float = 0.97, **overrides) -> ProposeRetrainingIntent:
    base = {
        "intent_text": "propose retraining fraud_v3",
        "process_ref": _process(),
        "model_id": _MODEL,
        "correlation_id": "corr-2",
        "confidence_score": confidence,
        "request_cost": _cost(),
    }
    base.update(overrides)
    return ProposeRetrainingIntent(**base)


def _proposal() -> RetrainingProposal:
    return RetrainingProposal(
        proposal_id="prop-fraud_v3-1",
        model_id=_MODEL,
        urgency=RetrainingUrgency.URGENT,
        rationale="drift high",
    )


def apply_intent(confidence: float = 1.0, **overrides) -> ApplyModelUpdateIntent:
    base = {
        "intent_text": "apply retraining to fraud_v3",
        "process_ref": _process(),
        "proposal": _proposal(),
        "correlation_id": "corr-3",
        "confidence_score": confidence,
        "request_cost": _cost(),
    }
    base.update(overrides)
    return ApplyModelUpdateIntent(**base)


# ── read / propose (AUTO-biased) ────────────────────────────────────────────


async def test_get_drift_signals_auto_proceeds():
    agent, port, recorder = make_agent()
    outcome = await agent.get_drift_signals(drift_intent(confidence=0.97))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.drift_calls == [_MODEL]
    assert recorder.records[0].action_taken == "GET_DRIFT_SIGNALS"
    assert outcome.requires_step_up is False


async def test_get_drift_signals_below_auto_band_defers():
    agent, port, recorder = make_agent()
    outcome = await agent.get_drift_signals(drift_intent(confidence=0.80))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.drift_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_propose_retraining_auto_proceeds_and_signals_dual_sign_off():
    agent, port, recorder = make_agent()
    outcome = await agent.propose_retraining(propose_intent(confidence=0.97))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert isinstance(outcome.result, RetrainingProposal)
    assert port.propose_calls == [_MODEL]
    # A proposal still requires the downstream CRO+CTO sign-off before it can become a change.
    assert outcome.requires_step_up is True
    assert recorder.records[0].action_taken == "PROPOSE_RETRAINING"
    # Proposing applied nothing.
    assert port.apply_calls == []


async def test_propose_retraining_below_auto_band_defers():
    agent, port, recorder = make_agent()
    outcome = await agent.propose_retraining(propose_intent(confidence=0.80))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"
    assert port.propose_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── I-27 DUAL CRO+CTO sign-off invariants (a/b/c/d) ─────────────────────────


async def test_apply_no_tokens_at_full_confidence_halts_dual_sign_off():
    # (a) apply @ confidence=1.0 with NO tokens → HALT, escalate→CRO+CTO, apply never called.
    agent, port, recorder = make_agent()
    outcome = await agent.apply_model_update(apply_intent(confidence=1.0))
    assert outcome.decision is ConfirmationDecision.AUTO  # band is AUTO; the dual gate still halts
    assert outcome.executed is False
    assert outcome.halt_reason == "dual_sign_off_required"
    assert outcome.requires_step_up is True
    assert outcome.escalated_to == "CRO+CTO"
    assert port.apply_calls == []  # the update was NEVER applied
    assert recorder.records[0].action_taken == "HALT_DUAL_SIGN_OFF_REQUIRED"
    assert recorder.records[0].escalated_to == "CRO+CTO"


async def test_apply_cro_token_only_halts_cto_missing():
    # (b) apply with CRO token only → HALT (CTO missing); apply never called.
    agent, port, _ = make_agent()
    outcome = await agent.apply_model_update(apply_intent(), cro_token=_CRO_TOKEN)
    assert outcome.executed is False
    assert outcome.halt_reason == "dual_sign_off_required"
    assert outcome.escalated_to == "CRO+CTO"
    assert port.apply_calls == []


async def test_apply_cto_token_only_halts_cro_missing():
    # (c) apply with CTO token only → HALT (CRO missing); apply never called.
    agent, port, _ = make_agent()
    outcome = await agent.apply_model_update(apply_intent(), cto_token=_CTO_TOKEN)
    assert outcome.executed is False
    assert outcome.halt_reason == "dual_sign_off_required"
    assert outcome.escalated_to == "CRO+CTO"
    assert port.apply_calls == []


async def test_apply_with_both_tokens_proceeds():
    # (d) apply with BOTH tokens → proceeds; the port is called with both tokens.
    agent, port, recorder = make_agent()
    outcome = await agent.apply_model_update(
        apply_intent(), cro_token=_CRO_TOKEN, cto_token=_CTO_TOKEN
    )
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert isinstance(outcome.result, ModelUpdateResult)
    assert outcome.result.applied is True
    assert port.apply_calls == [("prop-fraud_v3-1", _CRO_TOKEN, _CTO_TOKEN)]
    assert recorder.records[0].action_taken == "APPLY_MODEL_UPDATE"


async def test_apply_dual_sign_off_not_waivable_by_permissive_mask():
    # Config-floor invariant: a permissive mask (everything AUTO) cannot waive the dual sign-off.
    agent, port, recorder = make_agent(mask=make_mask(auto_threshold=0.0, review_floor=0.0))
    outcome = await agent.apply_model_update(apply_intent(confidence=0.0))
    assert outcome.executed is False
    assert outcome.halt_reason == "dual_sign_off_required"
    assert port.apply_calls == []


# ── shared §D2 gate-chain halts ─────────────────────────────────────────────


async def test_unresolved_process_ref_halts():
    agent, port, recorder = make_agent()
    intent = drift_intent(process_ref=ProcessRef(process_id="", version=""))
    outcome = await agent.get_drift_signals(intent)
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.drift_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_apply_refused():
    # An op not on the mask allow-list is refused outright — an ungoverned autonomous apply.
    agent, port, recorder = make_agent(mask=make_mask(scope=("MLSignalPort.get_drift_signals",)))
    outcome = await agent.apply_model_update(
        apply_intent(), cro_token=_CRO_TOKEN, cto_token=_CTO_TOKEN
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.apply_calls == []
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


async def test_block_low_confidence_on_read():
    agent, port, recorder = make_agent()
    outcome = await agent.get_drift_signals(drift_intent(confidence=0.50))
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "low_confidence"
    assert outcome.escalated_to is None
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_on_apply_escalates_dual():
    agent, port, recorder = make_agent()
    outcome = await agent.apply_model_update(
        apply_intent(confidence=0.50), cro_token=_CRO_TOKEN, cto_token=_CTO_TOKEN
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "low_confidence"
    assert outcome.escalated_to == "CRO+CTO"
    assert port.apply_calls == []


async def test_cost_cap_breach_per_request():
    agent, port, recorder = make_agent()
    outcome = await agent.get_drift_signals(drift_intent(request_cost=_cost(tokens=999_999)))
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert outcome.record.budget_breach_flag is BudgetBreach.BREACH
    assert port.drift_calls == []


async def test_cost_cap_breach_per_window():
    agent, port, _ = make_agent()
    agent._window.used_tokens = 99_950  # near the 100_000 window cap
    outcome = await agent.get_drift_signals(drift_intent(request_cost=_cost(tokens=100)))
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.drift_calls == []


async def test_compliance_block_escalates_to_cro():
    agent, port, recorder = make_agent()
    outcome = await agent.get_drift_signals(drift_intent(), compliance_result=ComplianceResult.FAIL)
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CRO"
    assert port.drift_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


async def test_provider_error_emits_lineage_and_reraises():
    agent, port, recorder = make_agent(raises=MLSignalSourceUnavailable("down", correlation_id="x"))
    with pytest.raises(MLSignalSourceUnavailable):
        await agent.get_drift_signals(drift_intent())
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken.startswith("HALT_PROVIDER_ERROR:")
    assert recorder.records[0].action_taken.endswith("MLSignalSourceUnavailable")


async def test_port_dual_sign_off_guard_is_defense_in_depth():
    # If the mask gate were somehow bypassed, the port's own DualSignOffRequired guard fires and
    # is surfaced as a provider error (emit + reraise) — defence-in-depth.
    agent, port, recorder = make_agent(
        raises=DualSignOffRequired("missing token", correlation_id="x")
    )
    with pytest.raises(DualSignOffRequired):
        await agent.apply_model_update(apply_intent(), cro_token=_CRO_TOKEN, cto_token=_CTO_TOKEN)
    assert recorder.records[0].action_taken.endswith("DualSignOffRequired")
    assert recorder.records[0].action_taken.startswith("HALT_PROVIDER_ERROR:")


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score must be in"):
        await agent.get_drift_signals(drift_intent(confidence=1.5))


# ── R-SEC + lineage obligation ──────────────────────────────────────────────


async def test_rsec_tokens_never_recorded_in_lineage():
    agent, port, recorder = make_agent()
    await agent.apply_model_update(apply_intent(), cro_token=_CRO_TOKEN, cto_token=_CTO_TOKEN)
    record = recorder.records[0]
    blob = repr(record)
    assert _CRO_TOKEN not in blob
    assert _CTO_TOKEN not in blob
    # A completed dual sign-off is recorded as the opaque roles only, never the token values.
    assert record.human_reviewed_by == "CRO+CTO"
    # Only opaque handles ride the triggering_event.
    assert record.triggering_event == "apply_model_update:prop-fraud_v3-1:fraud_v3"


async def test_exactly_one_lineage_record_per_action():
    agent, port, recorder = make_agent()
    await agent.get_drift_signals(drift_intent())
    await agent.propose_retraining(propose_intent())
    await agent.apply_model_update(apply_intent(), cro_token=_CRO_TOKEN, cto_token=_CTO_TOKEN)
    assert len(recorder.records) == 3
    assert all(r.agent_id == "ml_pipeline_agent" for r in recorder.records)


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.91, ConfirmationDecision.AUTO),
        (0.90, ConfirmationDecision.REVIEW),
        (0.70, ConfirmationDecision.REVIEW),
        (0.6999, ConfirmationDecision.BLOCK),
    ],
)
async def test_confidence_band_boundaries(confidence, expected):
    agent, _, _ = make_agent()
    outcome = await agent.get_drift_signals(drift_intent(confidence=confidence))
    assert outcome.decision is expected
