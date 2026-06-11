"""Comprehensive tests for DeployAgent — 100% coverage on deploy_agent.py.

Tests cover every branch of the governance engine (evaluate / _run_action):
  prepare AUTO happy path, HALT_REVIEW_DEFERRED, HALT_UNRESOLVED_PROCESS,
  REJECT_OUT_OF_SCOPE, BLOCK_LOW_CONFIDENCE, HALT_COST_CAP_BREACH (per-request
  tokens, per-request cost, per-window tokens, per-window cost),
  HALT_COMPLIANCE_BLOCK (escalate→CTO), HOLD_FOR_REVIEW (staging + production),
  DEPLOY_STAGING + DEPLOY_PRODUCTION happy paths, HALT_PROVIDER_ERROR (invalid
  token → port raises), confidence ValueError, band boundaries, R-SEC assertion,
  exactly-1-record invariant, and the critical production-never-autonomous invariant.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents._lineage import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    ProcessRef,
    RequestCost,
)
from services.agents.deploy_agent import (
    _TOKEN_PRESENT_MARKER,
    DeployAgent,
    DeployMask,
    DeployProductionIntent,
    DeployStagingIntent,
    PrepareDeploymentIntent,
)
from services.deploy.deploy_port import (
    DeployEnv,
    DeploymentPlan,
    DeployPortError,
    InMemoryDeployPort,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_TOKEN = "cto-secret-approval-token-xyz"
_DEFAULT_CAP = CostCap(
    max_request_tokens=5_000,
    max_request_cost=Decimal("5.00"),
    max_window_tokens=50_000,
    max_window_cost=Decimal("50.00"),
)
_SMALL_COST = RequestCost(tokens=100, cost=Decimal("0.10"))
_PROC = ProcessRef(process_id="DEPLOY-001", version="v1.0")
_UNRESOLVED = ProcessRef(process_id="", version="")

_STAGING_PLAN = DeploymentPlan(
    plan_id="plan-staging-001",
    target_env=DeployEnv.STAGING,
    artifact_ref="sha256:abc123",
    prepared_at="2026-06-11T00:00:00Z",
)
_PROD_PLAN = DeploymentPlan(
    plan_id="plan-production-001",
    target_env=DeployEnv.PRODUCTION,
    artifact_ref="sha256:abc123",
    prepared_at="2026-06-11T00:00:00Z",
)


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


def make_mask(**overrides: object) -> DeployMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return DeployMask(**base)  # type: ignore[arg-type]


def make_agent(
    *,
    mask: DeployMask | None = None,
    window: CostWindow | None = None,
    valid_tokens: set[str] | None = None,
    fail_on_call: bool = False,
) -> tuple[DeployAgent, InMemoryDeployPort, FakeRecorder]:
    port = InMemoryDeployPort(
        valid_tokens=valid_tokens if valid_tokens is not None else {_VALID_TOKEN},
        fail_on_call=fail_on_call,
    )
    rec = FakeRecorder()
    agent = DeployAgent(
        deploy_port=port,
        recorder=rec,
        mask=mask or make_mask(),
        cost_window=window,
    )
    return agent, port, rec


def prepare_intent(
    confidence: float = 0.95,
    env: DeployEnv = DeployEnv.STAGING,
    proc: ProcessRef = _PROC,
) -> PrepareDeploymentIntent:
    return PrepareDeploymentIntent(
        intent_text="prepare deployment",
        process_ref=proc,
        target_env=env,
        correlation_id="corr-prepare",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def staging_intent(
    confidence: float = 0.95,
    plan: DeploymentPlan = _STAGING_PLAN,
    proc: ProcessRef = _PROC,
) -> DeployStagingIntent:
    return DeployStagingIntent(
        intent_text="deploy to staging",
        process_ref=proc,
        plan=plan,
        correlation_id="corr-staging",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def prod_intent(
    confidence: float = 0.95,
    plan: DeploymentPlan = _PROD_PLAN,
    proc: ProcessRef = _PROC,
) -> DeployProductionIntent:
    return DeployProductionIntent(
        intent_text="deploy to production",
        process_ref=proc,
        plan=plan,
        correlation_id="corr-prod",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


# ---------------------------------------------------------------------------
# prepare_deployment — AUTO happy path
# ---------------------------------------------------------------------------


async def test_prepare_deployment_auto_happy_path() -> None:
    agent, port, rec = make_agent()
    outcome = await agent.prepare_deployment(prepare_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.result is not None
    assert isinstance(outcome.result, DeploymentPlan)
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "PREPARE_DEPLOYMENT"
    assert rec.records[0].human_reviewed_by is None


async def test_prepare_deployment_result_rides_on_outcome_only() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(prepare_intent(confidence=0.95))
    # result (DeploymentPlan) must be on AgentOutcome.result, never in the record
    assert outcome.result is not None
    assert not hasattr(rec.records[0], "result") or rec.records[0].result is None  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# prepare_deployment — HALT_REVIEW_DEFERRED (L1-Auto: REVIEW band → deferred)
# ---------------------------------------------------------------------------


async def test_prepare_deployment_review_band_halt_review_deferred() -> None:
    agent, port, rec = make_agent()
    execute_calls: list[object] = []
    original_prepare = port.prepare_deployment

    async def spy_prepare(env: DeployEnv) -> DeploymentPlan:
        execute_calls.append(env)
        return await original_prepare(env)

    port.prepare_deployment = spy_prepare  # type: ignore[method-assign]
    outcome = await agent.prepare_deployment(prepare_intent(confidence=0.80))
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert execute_calls == []  # port NOT called
    assert rec.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ---------------------------------------------------------------------------
# HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_halt_unresolved_process_ref_on_prepare() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(prepare_intent(proc=_UNRESOLVED))
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_halt_unresolved_process_ref_on_staging() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_staging(
        staging_intent(proc=_UNRESOLVED), approval_token=_VALID_TOKEN
    )
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"


async def test_halt_unresolved_process_ref_on_production() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_production(
        prod_intent(proc=_UNRESOLVED), approval_token=_VALID_TOKEN
    )
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"


# ---------------------------------------------------------------------------
# REJECT_OUT_OF_SCOPE — no bypass invariant
# ---------------------------------------------------------------------------


async def test_reject_out_of_scope_op_not_on_allow_list() -> None:
    mask = make_mask(scope=("DeployPort.prepare_deployment",))
    agent, _, rec = make_agent(mask=mask)
    # deploy_staging uses op "DeployPort.execute_deployment" which is not in scope
    outcome = await agent.deploy_staging(staging_intent(), approval_token=_VALID_TOKEN)
    assert outcome.halt_reason == "out_of_scope"
    assert rec.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


async def test_reject_autonomous_execute_not_on_allow_list() -> None:
    # "DeployPort.autonomous_execute" MUST be out-of-scope (proves no bypass exists)
    mask = make_mask()
    assert "DeployPort.autonomous_execute" not in mask.scope


# ---------------------------------------------------------------------------
# BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence_on_prepare() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(prepare_intent(confidence=0.50))
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_on_staging() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_staging(
        staging_intent(confidence=0.50), approval_token=_VALID_TOKEN
    )
    assert outcome.halt_reason == "low_confidence"
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# STAGING L2 — HOLD_FOR_REVIEW (no token)
# ---------------------------------------------------------------------------


async def test_staging_no_token_hold_for_review() -> None:
    agent, port, rec = make_agent()
    execute_calls: list[object] = []
    original = port.execute_deployment

    async def spy(*args: object, **kwargs: object) -> object:
        execute_calls.append(args)
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    port.execute_deployment = spy  # type: ignore[method-assign]
    outcome = await agent.deploy_staging(staging_intent(), approval_token=None)
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.escalated_to == "CTO"
    assert execute_calls == []  # port.execute NOT called
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "CTO"


async def test_staging_force_review_overrides_auto_band_no_token() -> None:
    # Even at confidence=1.0 (AUTO), force_review pulls staging to REVIEW → HOLD
    agent, port, rec = make_agent()
    execute_calls: list[object] = []
    port_original = port.execute_deployment

    async def spy(*args: object, **kwargs: object) -> object:
        execute_calls.append(args)
        return await port_original(*args, **kwargs)  # type: ignore[arg-type]

    port.execute_deployment = spy  # type: ignore[method-assign]
    outcome = await agent.deploy_staging(staging_intent(confidence=1.0), approval_token=None)
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert execute_calls == []


# ---------------------------------------------------------------------------
# STAGING L2 — executes with valid token
# ---------------------------------------------------------------------------


async def test_staging_with_valid_token_executes() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_staging(staging_intent(), approval_token=_VALID_TOKEN)
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "DEPLOY_STAGING"
    assert rec.records[0].human_reviewed_by == _TOKEN_PRESENT_MARKER


# ---------------------------------------------------------------------------
# PRODUCTION L3 — HOLD (SAFETY INVARIANT TESTS)
# ---------------------------------------------------------------------------


async def test_production_no_token_halt_at_confidence_100() -> None:
    """INVARIANT: production deploy at confidence=1.0 with no token → HALT."""
    agent, port, rec = make_agent()
    execute_calls: list[object] = []
    port_original = port.execute_deployment

    async def spy(*args: object, **kwargs: object) -> object:
        execute_calls.append(args)
        return await port_original(*args, **kwargs)  # type: ignore[arg-type]

    port.execute_deployment = spy  # type: ignore[method-assign]
    outcome = await agent.deploy_production(prod_intent(confidence=1.0), approval_token=None)
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_step_up is True
    assert outcome.escalated_to == "CTO"
    assert execute_calls == []  # port.execute NEVER called — invariant holds


async def test_production_no_token_hold_requires_step_up() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_production(prod_intent(), approval_token=None)
    assert outcome.requires_step_up is True
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "CTO"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "CTO"


async def test_production_invariant_no_autonomous_execute_spy() -> None:
    """Spy on port.execute_deployment: NEVER called for production without token."""
    agent, port, rec = make_agent()
    called: list[tuple[object, ...]] = []

    async def recording_execute(plan: object, token: object) -> object:
        called.append((plan, token))
        raise DeployPortError("should never be reached")

    port.execute_deployment = recording_execute  # type: ignore[method-assign]
    outcome = await agent.deploy_production(prod_intent(confidence=0.95), approval_token=None)
    assert called == []  # spy never fired — invariant holds
    assert outcome.executed is False


# ---------------------------------------------------------------------------
# PRODUCTION L3 — executes with valid token
# ---------------------------------------------------------------------------


async def test_production_with_valid_token_executes() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_production(prod_intent(), approval_token=_VALID_TOKEN)
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "DEPLOY_PRODUCTION"
    assert rec.records[0].human_reviewed_by == _TOKEN_PRESENT_MARKER


# ---------------------------------------------------------------------------
# PRODUCTION L3 — invalid token → HALT_PROVIDER_ERROR (defense-in-depth)
# ---------------------------------------------------------------------------


async def test_production_invalid_token_raises_deploy_port_error() -> None:
    port = InMemoryDeployPort(valid_tokens={"real-token"})
    rec = FakeRecorder()
    agent = DeployAgent(deploy_port=port, recorder=rec, mask=make_mask())
    with pytest.raises(DeployPortError):
        await agent.deploy_production(prod_intent(), approval_token="WRONG-TOKEN")
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


async def test_staging_invalid_token_raises_deploy_port_error() -> None:
    port = InMemoryDeployPort(valid_tokens={"real-token"})
    rec = FakeRecorder()
    agent = DeployAgent(deploy_port=port, recorder=rec, mask=make_mask())
    with pytest.raises(DeployPortError):
        await agent.deploy_staging(staging_intent(), approval_token="WRONG-TOKEN")
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


# ---------------------------------------------------------------------------
# HALT_COST_CAP_BREACH — four sub-cases
# ---------------------------------------------------------------------------


async def test_halt_cost_cap_per_request_tokens() -> None:
    cap = CostCap(
        max_request_tokens=50,  # _SMALL_COST = 100 tokens > 50
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50_000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.prepare_deployment(prepare_intent())
    assert outcome.halt_reason == "cost_cap_breach"
    assert rec.records[0].budget_breach_flag is BudgetBreach.BREACH


async def test_halt_cost_cap_per_request_cost() -> None:
    cap = CostCap(
        max_request_tokens=5_000,
        max_request_cost=Decimal("0.05"),  # _SMALL_COST = 0.10 > 0.05
        max_window_tokens=50_000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.prepare_deployment(prepare_intent())
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_tokens() -> None:
    cap = CostCap(
        max_request_tokens=5_000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=150,  # used=100 + 100 = 200 > 150
        max_window_cost=Decimal("100.00"),
    )
    window = CostWindow(used_tokens=100)
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.prepare_deployment(prepare_intent())
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_cost() -> None:
    cap = CostCap(
        max_request_tokens=5_000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50_000,
        max_window_cost=Decimal("0.15"),  # used=0.10 + 0.10 = 0.20 > 0.15
    )
    window = CostWindow(used_cost=Decimal("0.10"))
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.prepare_deployment(prepare_intent())
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# HALT_COMPLIANCE_BLOCK — escalates to CTO
# ---------------------------------------------------------------------------


async def test_halt_compliance_fail_escalates_to_cto() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(
        prepare_intent(),
        compliance_result=ComplianceResult.FAIL,
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CTO"
    assert rec.records[0].escalated_to == "CTO"
    assert rec.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


async def test_halt_compliance_escalate_also_blocks() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.deploy_staging(
        staging_intent(),
        approval_token=_VALID_TOKEN,
        compliance_result=ComplianceResult.ESCALATE,
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CTO"


async def test_compliance_na_is_allowed() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(
        prepare_intent(),
        compliance_result=ComplianceResult.NA,
    )
    assert outcome.executed is True


# ---------------------------------------------------------------------------
# Confidence ValueError
# ---------------------------------------------------------------------------


async def test_confidence_above_one_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.prepare_deployment(prepare_intent(confidence=1.01))


async def test_confidence_below_zero_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.prepare_deployment(prepare_intent(confidence=-0.01))


# ---------------------------------------------------------------------------
# Band boundaries
# ---------------------------------------------------------------------------


async def test_band_boundary_exactly_090_is_auto_for_prepare() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(prepare_intent(confidence=0.90))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True


async def test_band_boundary_exactly_070_is_review_deferred_for_prepare() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.prepare_deployment(prepare_intent(confidence=0.70))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


async def test_band_boundary_exactly_090_staging_force_review_hold() -> None:
    # At 0.90 (AUTO band), force_review for staging pulls to REVIEW → HOLD (no token)
    agent, _, rec = make_agent()
    outcome = await agent.deploy_staging(staging_intent(confidence=0.90), approval_token=None)
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "hitl_review_required"


# ---------------------------------------------------------------------------
# R-SEC: approval_token MUST NOT appear in any AgentDecisionRecord field
# ---------------------------------------------------------------------------


async def test_rsec_token_not_in_staging_record() -> None:
    agent, _, rec = make_agent()
    await agent.deploy_staging(staging_intent(), approval_token=_VALID_TOKEN)
    r = rec.records[0]
    # The raw token MUST NOT appear in any record field
    for field_val in [
        r.triggering_event,
        r.intent,
        str(r.human_reviewed_by or ""),
        r.reasoning_summary,
        str(r.escalated_to or ""),
        r.action_taken,
        r.agent_id,
        r.correlation_id,
    ]:
        assert _VALID_TOKEN not in field_val, f"token found in field: {field_val!r}"
    # human_reviewed_by must be the presence marker, not the raw token
    assert r.human_reviewed_by == _TOKEN_PRESENT_MARKER


async def test_rsec_token_not_in_production_record() -> None:
    agent, _, rec = make_agent()
    await agent.deploy_production(prod_intent(), approval_token=_VALID_TOKEN)
    r = rec.records[0]
    for field_val in [
        r.triggering_event,
        r.intent,
        str(r.human_reviewed_by or ""),
        r.reasoning_summary,
        str(r.escalated_to or ""),
        r.action_taken,
    ]:
        assert _VALID_TOKEN not in field_val, f"token found in field: {field_val!r}"
    assert r.human_reviewed_by == _TOKEN_PRESENT_MARKER


async def test_rsec_triggering_event_is_opaque_handle_only() -> None:
    agent, _, rec = make_agent()
    await agent.deploy_production(prod_intent(), approval_token=_VALID_TOKEN)
    r = rec.records[0]
    # triggering_event is plan_id:target_env only — no token, no artifact_ref
    assert r.triggering_event == f"deploy_production:{_PROD_PLAN.plan_id}:{_PROD_PLAN.target_env}"
    assert "sha256" not in r.triggering_event  # artifact_ref not exposed
    assert _VALID_TOKEN not in r.triggering_event


async def test_rsec_no_token_holder_on_hold_record() -> None:
    agent, _, rec = make_agent()
    await agent.deploy_production(prod_intent(), approval_token=None)
    r = rec.records[0]
    assert r.human_reviewed_by is None


# ---------------------------------------------------------------------------
# Exactly 1 record per action
# ---------------------------------------------------------------------------


async def test_exactly_one_record_per_action() -> None:
    agent, _, rec = make_agent()
    await agent.prepare_deployment(prepare_intent(confidence=0.95))
    await agent.prepare_deployment(prepare_intent(confidence=0.80))  # HALT_REVIEW_DEFERRED
    await agent.deploy_staging(staging_intent(), approval_token=None)  # HOLD
    await agent.deploy_staging(staging_intent(), approval_token=_VALID_TOKEN)
    await agent.deploy_production(prod_intent(), approval_token=_VALID_TOKEN)
    assert len(rec.records) == 5


async def test_provider_error_emits_exactly_one_record_then_reraises() -> None:
    port = InMemoryDeployPort(valid_tokens={"real-token"})
    rec = FakeRecorder()
    agent = DeployAgent(deploy_port=port, recorder=rec, mask=make_mask())
    with pytest.raises(DeployPortError):
        await agent.deploy_production(prod_intent(), approval_token="WRONG")
    assert len(rec.records) == 1


# ---------------------------------------------------------------------------
# Window accumulates on success, not on halt
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_prepare_success() -> None:
    agent, _, _ = make_agent()
    assert agent._window.used_tokens == 0
    await agent.prepare_deployment(prepare_intent(confidence=0.95))
    assert agent._window.used_tokens == 100
    assert agent._window.used_cost == Decimal("0.10")


async def test_window_not_accumulated_on_halt() -> None:
    agent, _, _ = make_agent()
    await agent.prepare_deployment(prepare_intent(proc=_UNRESOLVED))
    assert agent._window.used_tokens == 0


# ---------------------------------------------------------------------------
# Default mask scope contains all 3 ops, no autonomous bypass
# ---------------------------------------------------------------------------


def test_default_mask_scope_contains_required_ops() -> None:
    mask = make_mask()
    assert "DeployPort.prepare_deployment" in mask.scope
    assert "DeployPort.request_approval" in mask.scope
    assert "DeployPort.execute_deployment" in mask.scope
    assert "DeployPort.autonomous_execute" not in mask.scope
