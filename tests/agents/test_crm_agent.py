"""Tests for the ADR-049 Referral / CRM mask agent (services/agents/crm_agent.py).

Covers every mask path in the §D2 gate-chain order:
AUTO routine referral registration, the payout-linked override → forced REVIEW
HITL hold then proceed-with-reviewer (regardless of confidence), anti-abuse
(self-referral / duplicate pair) → BLOCK + AML escalation, PII-gate fail on
get_user → BLOCK + DPO escalation, the AUTO resolve_referral_code read and its
below-AUTO re-check halt, get_user AUTO read, update_user_tier AUTO and its
payout-linked REVIEW, cost-cap breach (per-request and per-window), BLOCK on low
confidence, out-of-scope refusal, unresolved process_ref, provider-error lineage,
and the lineage-per-action obligation (ADR-046). The port and the recorder are
fakes — the agent is exercised as pure governance logic with no live infra.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.crm_agent import (
    AgentDecisionRecord,
    AutonomyLevel,
    BudgetBreach,
    ComplianceOverlay,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    CRMAgent,
    CRMMask,
    DecisionRecorder,
    GetUserIntent,
    ProcessRef,
    RegisterReferralIntent,
    RequestCost,
    ResolveCodeIntent,
    UpdateTierIntent,
)
from services.crm.crm_provider_port import (
    CRMProviderPort,
    CRMUser,
    CRMUserId,
    ReferralEvent,
    RegisterReferralResult,
    SelfReferral,
    ValidationError,
)

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeCRMProviderPort(CRMProviderPort):
    """In-test CRMProviderPort double. Records calls; returns canned results or
    raises a configured error so the agent's governance logic is exercised without
    any live provider."""

    def __init__(
        self,
        *,
        register_result: RegisterReferralResult | None = None,
        resolve_result: CRMUserId | None = "owner-1",
        user_result: CRMUser | None = None,
        register_raises: Exception | None = None,
    ) -> None:
        self._register_result = register_result or RegisterReferralResult(accepted=True)
        self._resolve_result = resolve_result
        self._user_result = user_result if user_result is not None else CRMUser(user_id="u1")
        self._register_raises = register_raises
        self.register_calls: list[ReferralEvent] = []
        self.resolve_calls: list[str] = []
        self.get_user_calls: list[str] = []
        self.update_tier_calls: list[tuple[str, str, str]] = []

    async def register_referral(self, event: ReferralEvent) -> RegisterReferralResult:
        self.register_calls.append(event)
        if self._register_raises is not None:
            raise self._register_raises
        return self._register_result

    async def resolve_referral_code(self, code: str) -> CRMUserId | None:
        self.resolve_calls.append(code)
        return self._resolve_result

    async def get_user(self, user_id: str) -> CRMUser | None:
        self.get_user_calls.append(user_id)
        return self._user_result

    async def update_user_tier(self, user_id: str, tier: str, correlation_id: str) -> None:
        self.update_tier_calls.append((user_id, tier, correlation_id))


# ── Builders ──────────────────────────────────────────────────────────────────


def make_mask(**overrides) -> CRMMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return CRMMask(**base)


def make_agent(
    *,
    mask: CRMMask | None = None,
    port: FakeCRMProviderPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[CRMAgent, FakeCRMProviderPort, FakeRecorder]:
    port = port or FakeCRMProviderPort()
    recorder = recorder or FakeRecorder()
    agent = CRMAgent(
        provider_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-CRM", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_register_intent(
    *,
    confidence: float = 0.95,
    cost: RequestCost | None = None,
    resolved: bool = True,
    payout_linked: bool = False,
    referrer: str = "ref-1",
    referee: str = "ref-2",
) -> RegisterReferralIntent:
    return RegisterReferralIntent(
        intent_text="Register my friend's referral",
        process_ref=_ref(resolved),
        referrer=referrer,
        referee=referee,
        code="CODE-123",
        occurred_at="2026-06-07T00:00:00Z",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=200, cost=Decimal("0.02")),
        payout_linked=payout_linked,
    )


def make_resolve_intent(
    *, confidence: float = 0.99, cost: RequestCost | None = None
) -> ResolveCodeIntent:
    return ResolveCodeIntent(
        intent_text="Who owns this referral code?",
        process_ref=_ref(),
        code="CODE-123",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=20, cost=Decimal("0.005")),
    )


def make_get_user_intent(
    *, confidence: float = 0.99, cost: RequestCost | None = None
) -> GetUserIntent:
    return GetUserIntent(
        intent_text="Fetch the user profile",
        process_ref=_ref(),
        user_id="u1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=30, cost=Decimal("0.006")),
    )


def make_tier_intent(
    *,
    confidence: float = 0.95,
    cost: RequestCost | None = None,
    payout_linked: bool = False,
) -> UpdateTierIntent:
    return UpdateTierIntent(
        intent_text="Promote this user to premium",
        process_ref=_ref(),
        user_id="u1",
        tier="premium",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=200, cost=Decimal("0.02")),
        payout_linked=payout_linked,
    )


# ── AUTO routine referral registration ───────────────────────────────────────────


async def test_auto_routine_referral_executes_no_hitl():
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(make_register_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.requires_step_up is False
    assert len(port.register_calls) == 1
    assert recorder.records[0].action_taken == "REGISTER_REFERRAL"
    assert len(recorder.records) == 1


async def test_register_result_surfaced_on_outcome():
    port = FakeCRMProviderPort(register_result=RegisterReferralResult(accepted=True))
    agent, port, _ = make_agent(port=port)
    outcome = await agent.register_referral(make_register_intent())
    assert isinstance(outcome.result, RegisterReferralResult)
    assert outcome.result.accepted is True


async def test_contract_rejection_reason_surfaced_when_compliance_passes():
    # Defense-in-depth: even when the agent's anti-abuse gate PASSes, the port may
    # still reject a self-referral; the CONTRACT reason is surfaced verbatim.
    port = FakeCRMProviderPort(
        register_result=RegisterReferralResult(accepted=False, reason="self_referral")
    )
    agent, port, recorder = make_agent(port=port)
    outcome = await agent.register_referral(make_register_intent())
    assert outcome.executed is True
    assert outcome.result.accepted is False
    assert outcome.result.reason == "self_referral"
    assert recorder.records[0].action_taken == "REGISTER_REFERRAL"


# ── Payout-linked override: forced REVIEW regardless of confidence ────────────────


async def test_payout_linked_referral_forces_review_hold_even_at_auto_confidence():
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(
        make_register_intent(confidence=0.99, payout_linked=True)
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert outcome.halt_reason == "hitl_review_required"
    assert port.register_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert recorder.records[0].human_reviewed_by is None
    assert "ADR-049-D3-payout-linked-REVIEW" in recorder.records[0].policies_evaluated


async def test_payout_linked_referral_proceeds_with_reviewer():
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(
        make_register_intent(confidence=0.99, payout_linked=True),
        human_reviewed_by="ops@banxe",
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert len(port.register_calls) == 1
    assert recorder.records[0].action_taken == "REGISTER_REFERRAL"
    assert recorder.records[0].human_reviewed_by == "ops@banxe"


async def test_non_payout_review_band_holds_for_hitl():
    # A routine referral in the REVIEW band still holds for HITL (not payout-tagged).
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(make_register_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.register_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-049-D3-payout-linked-REVIEW" not in recorder.records[0].policies_evaluated


# ── Anti-abuse overlay (self-referral / duplicate pair) → BLOCK + AML ─────────────


async def test_anti_abuse_self_referral_verdict_blocks_and_escalates_aml():
    # The L3 anti-abuse overlay classifies the self-referral upstream; the agent
    # BLOCKs before the port is ever called and escalates to AML.
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(
        make_register_intent(referrer="same", referee="same"),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "AML"
    assert port.register_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].escalated_to == "AML"


async def test_anti_abuse_duplicate_pair_verdict_blocks_and_escalates_aml():
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(
        make_register_intent(),
        compliance_result=ComplianceResult.ESCALATE,
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.register_calls == []
    assert recorder.records[0].escalated_to == "AML"


async def test_provider_self_referral_error_records_then_raises():
    # If the port itself raises (defense-in-depth), lineage is emitted then re-raised.
    port = FakeCRMProviderPort(
        register_raises=SelfReferral("referrer == referee", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(SelfReferral):
        await agent.register_referral(make_register_intent(confidence=0.95))

    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:SelfReferral"


# ── PII overlay (ADR-016) on get_user ────────────────────────────────────────────


async def test_get_user_auto_read_executes():
    port = FakeCRMProviderPort(user_result=CRMUser(user_id="u1", tier="premium"))
    agent, port, recorder = make_agent(port=port)
    outcome = await agent.get_user(make_get_user_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert port.get_user_calls == ["u1"]
    assert outcome.result.tier == "premium"
    assert recorder.records[0].action_taken == "GET_USER"
    assert len(recorder.records) == 1


async def test_get_user_pii_fail_blocks_and_escalates_dpo():
    agent, port, recorder = make_agent()
    outcome = await agent.get_user(make_get_user_intent(), compliance_result=ComplianceResult.FAIL)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "DPO"
    assert port.get_user_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].escalated_to == "DPO"


async def test_get_user_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.get_user(make_get_user_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.get_user_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── resolve_referral_code: AUTO read + below-AUTO re-check ────────────────────────


async def test_resolve_referral_code_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.resolve_referral_code(make_resolve_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert port.resolve_calls == ["CODE-123"]
    assert outcome.result == "owner-1"
    assert recorder.records[0].action_taken == "RESOLVE_REFERRAL_CODE"
    assert len(recorder.records) == 1


async def test_resolve_referral_code_unknown_returns_none():
    port = FakeCRMProviderPort(resolve_result=None)
    agent, port, _ = make_agent(port=port)
    outcome = await agent.resolve_referral_code(make_resolve_intent(confidence=0.99))
    assert outcome.executed is True
    assert outcome.result is None


async def test_resolve_referral_code_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.resolve_referral_code(make_resolve_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.resolve_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── update_user_tier: AUTO + payout-linked REVIEW ────────────────────────────────


async def test_update_tier_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.update_user_tier(make_tier_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.update_tier_calls == [("u1", "premium", "corr-1")]
    assert recorder.records[0].action_taken == "UPDATE_USER_TIER"


async def test_update_tier_payout_linked_forces_review_hold():
    agent, port, recorder = make_agent()
    outcome = await agent.update_user_tier(make_tier_intent(confidence=0.99, payout_linked=True))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.update_tier_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-049-D3-payout-linked-REVIEW" in recorder.records[0].policies_evaluated


async def test_update_tier_payout_linked_proceeds_with_reviewer():
    agent, port, recorder = make_agent()
    outcome = await agent.update_user_tier(
        make_tier_intent(confidence=0.99, payout_linked=True),
        human_reviewed_by="ops@banxe",
    )
    assert outcome.executed is True
    assert port.update_tier_calls == [("u1", "premium", "corr-1")]
    assert recorder.records[0].human_reviewed_by == "ops@banxe"


async def test_update_tier_pii_abuse_fail_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.update_user_tier(
        make_tier_intent(), compliance_result=ComplianceResult.FAIL
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.update_tier_calls == []
    assert outcome.escalated_to == "AML"


# ── BLOCK / scope / process resolution ───────────────────────────────────────────


async def test_block_low_confidence_register():
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(make_register_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.register_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_read():
    agent, port, recorder = make_agent()
    outcome = await agent.resolve_referral_code(make_resolve_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.resolve_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.register_referral(make_register_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.register_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright (ADR-049 §D3).
    agent, port, recorder = make_agent(
        mask=make_mask(scope=("CRMProviderPort.resolve_referral_code",))
    )
    outcome = await agent.register_referral(make_register_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.register_calls == []
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


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
    outcome = await agent.register_referral(
        make_register_intent(confidence=confidence), human_reviewed_by="ops@banxe"
    )
    assert outcome.decision is expected


# ── Cost-cap breach ──────────────────────────────────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, port, recorder = make_agent()
    intent = make_register_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.register_referral(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.register_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.register_referral(
        make_register_intent(cost=RequestCost(tokens=200, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.register_calls == []


async def test_window_accumulates_on_successful_action():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.register_referral(
        make_register_intent(cost=RequestCost(tokens=300, cost=Decimal("0.02")))
    )
    assert window.used_tokens == 300
    assert window.used_cost == Decimal("0.02")


# ── Provider error → lineage then re-raise ───────────────────────────────────────


async def test_provider_validation_error_records_then_raises():
    port = FakeCRMProviderPort(
        register_raises=ValidationError("empty user_id", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ValidationError):
        await agent.register_referral(make_register_intent(confidence=0.95))

    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:ValidationError"


# ── Lineage obligation (ADR-046) ─────────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.register_referral(make_register_intent())
    await agent.register_referral(make_register_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "crm_agent"
    assert rec.intent == "Register my friend's referral"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 200
    assert rec.cost_amount == Decimal("0.02")
    assert rec.budget_window_ref == "crm_agent:default"


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.register_referral(make_register_intent(confidence=1.5))


# ── Mask config-as-data ──────────────────────────────────────────────────────────


async def test_mask_is_auto_biased_with_pii_and_anti_abuse_gate():
    mask = make_mask()
    assert mask.autonomy_level is AutonomyLevel.AUTO_BIASED
    assert mask.compliance_gate == ("PII", "ANTI_ABUSE")
    assert mask.dpo_role == "DPO"
    assert mask.abuse_role == "AML"
    assert "CRMProviderPort.register_referral" in mask.scope
    assert "CRMProviderPort.update_user_tier" in mask.scope


async def test_custom_escalation_roles_used():
    agent, _, recorder = make_agent(mask=make_mask(dpo_role="DataOfficer", abuse_role="FraudOps"))
    pii = await agent.get_user(make_get_user_intent(), compliance_result=ComplianceResult.FAIL)
    abuse = await agent.register_referral(
        make_register_intent(), compliance_result=ComplianceResult.FAIL
    )
    assert pii.escalated_to == "DataOfficer"
    assert abuse.escalated_to == "FraudOps"


async def test_compliance_overlay_routing_values():
    # PII overlay → DPO; anti-abuse overlay → AML (escalation routing is overlay-keyed).
    assert ComplianceOverlay.PII.value == "PII"
    assert ComplianceOverlay.ANTI_ABUSE.value == "ANTI_ABUSE"
