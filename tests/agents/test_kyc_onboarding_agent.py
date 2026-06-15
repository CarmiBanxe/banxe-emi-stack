"""Tests for the ADR-049 KYC onboarding mask agent
(services/agents/kyc_onboarding_agent.py).

Covers every mask path in the §D2 gate-chain order:
AUTO read (check_status), REVIEW→HITL hold then proceed for the REVIEW-biased
session start, identity-decision mandatory HITL (hold + proceed) with MLRO
escalation, BLOCK on low confidence, out-of-scope refusal, cost-cap breach
(per-request and per-window), biometric step-up required for identity decisions,
compliance fail/escalate → MLRO escalation, blocked tier downgrade → MLRO
escalation, the DECLINE (no provider mutation) path, webhook idempotency +
signature verification + provider-error escalation, and the lineage-per-action
obligation (ADR-046). The port and the recorder are fakes — the agent is
exercised as pure governance logic with no live infra.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.kyc_onboarding_agent import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    IdentityDecision,
    IdentityDecisionIntent,
    KYCOnboardingAgent,
    KYCOnboardingMask,
    ProcessRef,
    RequestCost,
    StartOnboardingIntent,
    StatusCheckIntent,
)
from services.kyc.kyc_provider_port import (
    InvalidSignature,
    KYCProviderPort,
    KYCResult,
    KYCSession,
    KYCStatus,
    KYCTier,
    ProviderUnavailable,
    TierDowngradeBlocked,
    WebhookOutcome,
)

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeKYCProviderPort(KYCProviderPort):
    """In-test KYCProviderPort double. Records calls; returns canned results or
    raises a configured error per op so the agent's governance logic is exercised
    without any live provider."""

    def __init__(
        self,
        *,
        session: KYCSession | None = None,
        status: KYCResult | None = None,
        change_result: KYCResult | None = None,
        webhook: WebhookOutcome | None = None,
        change_raises: Exception | None = None,
        webhook_raises: Exception | None = None,
    ) -> None:
        self._session = session or KYCSession(
            user_id="u1",
            access_token="tok_1",
            expires_at="2026-06-08T00:00:00Z",
            provider_level_id="lvl_basic",
            correlation_id="corr-1",
        )
        self._status = status or KYCResult(
            user_id="u1",
            status=KYCStatus.PENDING,
            tier=KYCTier.BASIC,
            provider_level_id="lvl_basic",
        )
        self._change_result = change_result or KYCResult(
            user_id="u1",
            status=KYCStatus.APPROVED,
            tier=KYCTier.FULL,
            provider_level_id="lvl_full",
        )
        self._webhook = webhook or WebhookOutcome(
            processed=True, deduped=False, user_id="u1", new_status=KYCStatus.APPROVED
        )
        self._change_raises = change_raises
        self._webhook_raises = webhook_raises
        self.start_calls: list[tuple[str, KYCTier, str]] = []
        self.status_calls: list[str] = []
        self.change_calls: list[tuple[str, KYCTier, str]] = []
        self.webhook_calls: list[tuple[object, str]] = []

    async def start_session(self, user_id: str, tier: KYCTier, correlation_id: str) -> KYCSession:
        self.start_calls.append((user_id, tier, correlation_id))
        return self._session

    async def get_status(self, user_id: str) -> KYCResult:
        self.status_calls.append(user_id)
        return self._status

    async def handle_webhook(self, payload: object, signature: str) -> WebhookOutcome:
        self.webhook_calls.append((payload, signature))
        if self._webhook_raises is not None:
            raise self._webhook_raises
        return self._webhook

    async def change_level(self, user_id: str, new_tier: KYCTier, correlation_id: str) -> KYCResult:
        self.change_calls.append((user_id, new_tier, correlation_id))
        if self._change_raises is not None:
            raise self._change_raises
        return self._change_result


# ── Builders ──────────────────────────────────────────────────────────────────


def make_mask(**overrides) -> KYCOnboardingMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return KYCOnboardingMask(**base)


def make_agent(
    *,
    mask: KYCOnboardingMask | None = None,
    port: FakeKYCProviderPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[KYCOnboardingAgent, FakeKYCProviderPort, FakeRecorder]:
    port = port or FakeKYCProviderPort()
    recorder = recorder or FakeRecorder()
    agent = KYCOnboardingAgent(
        provider_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-KYC-ONBOARD", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_start_intent(
    *, confidence: float = 0.95, cost: RequestCost | None = None, resolved: bool = True
) -> StartOnboardingIntent:
    return StartOnboardingIntent(
        intent_text="Start my identity verification",
        process_ref=_ref(resolved),
        user_id="u1",
        tier=KYCTier.BASIC,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=400, cost=Decimal("0.04")),
    )


def make_status_intent(*, confidence: float = 0.99) -> StatusCheckIntent:
    return StatusCheckIntent(
        intent_text="What is my KYC status?",
        process_ref=_ref(),
        user_id="u1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.01")),
    )


def make_identity_intent(
    *,
    decision: IdentityDecision = IdentityDecision.ACCEPT,
    confidence: float = 0.95,
    biometric_required: bool = True,
    biometric_verified: bool = True,
    target_tier: KYCTier = KYCTier.FULL,
) -> IdentityDecisionIntent:
    return IdentityDecisionIntent(
        intent_text="Accept this client's identity verification",
        process_ref=_ref(),
        user_id="u1",
        decision=decision,
        target_tier=target_tier,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=600, cost=Decimal("0.06")),
        biometric_required=biometric_required,
        biometric_verified=biometric_verified,
    )


# ── AUTO read path (check_status) ──────────────────────────────────────────────


async def test_auto_check_status_executes_no_hitl():
    agent, port, recorder = make_agent()
    outcome = await agent.check_status(make_status_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_step_up is False
    assert outcome.requires_hitl is False
    assert port.status_calls == ["u1"]
    assert recorder.records[0].action_taken == "CHECK_KYC_STATUS"
    assert len(recorder.records) == 1


async def test_read_below_auto_band_halts_for_recheck():
    # Reads are AUTO-only: a below-AUTO read halts (re-check), not a HITL hold.
    agent, port, recorder = make_agent()
    outcome = await agent.check_status(make_status_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.status_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── REVIEW-biased session start (HITL hold + proceed) ──────────────────────────


async def test_start_onboarding_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.start_onboarding(make_start_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.start_calls == [("u1", KYCTier.BASIC, "corr-1")]
    assert recorder.records[0].action_taken == "START_KYC_SESSION"


async def test_start_onboarding_review_band_holds_for_hitl():
    agent, port, recorder = make_agent()
    outcome = await agent.start_onboarding(make_start_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.start_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert recorder.records[0].human_reviewed_by is None


async def test_start_onboarding_review_with_reviewer_proceeds():
    agent, port, recorder = make_agent()
    outcome = await agent.start_onboarding(
        make_start_intent(confidence=0.80), human_reviewed_by="mlro@banxe"
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert port.start_calls == [("u1", KYCTier.BASIC, "corr-1")]
    assert recorder.records[0].human_reviewed_by == "mlro@banxe"
    assert recorder.records[0].action_taken == "START_KYC_SESSION"


# ── Identity decision: mandatory HITL, biometric, change_level ──────────────────


async def test_identity_accept_requires_human_even_at_auto():
    # Mandatory HITL: an identity decision holds even at AUTO confidence with no reviewer.
    agent, port, recorder = make_agent()
    outcome = await agent.accept_or_decline_identity(make_identity_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "MLRO"
    assert port.change_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-049-D3-identity-HITL" in recorder.records[0].policies_evaluated


async def test_identity_accept_with_reviewer_and_biometric_changes_level():
    agent, port, recorder = make_agent()
    outcome = await agent.accept_or_decline_identity(
        make_identity_intent(confidence=0.99, biometric_verified=True),
        human_reviewed_by="mlro@banxe",
    )

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert port.change_calls == [("u1", KYCTier.FULL, "corr-1")]
    assert recorder.records[0].action_taken == "ACCEPT_IDENTITY"
    assert recorder.records[0].human_reviewed_by == "mlro@banxe"


async def test_identity_decline_records_verdict_without_provider_call():
    agent, port, recorder = make_agent()
    outcome = await agent.accept_or_decline_identity(
        make_identity_intent(decision=IdentityDecision.DECLINE, biometric_required=False),
        human_reviewed_by="mlro@banxe",
    )

    assert outcome.executed is True  # decision committed (recorded), no provider mutation
    assert outcome.result is None
    assert port.change_calls == []
    assert recorder.records[0].action_taken == "DECLINE_IDENTITY"


async def test_identity_biometric_required_halts_step_up():
    agent, port, recorder = make_agent()
    outcome = await agent.accept_or_decline_identity(
        make_identity_intent(confidence=0.99, biometric_required=True, biometric_verified=False),
        human_reviewed_by="mlro@banxe",
    )

    assert outcome.executed is False
    assert outcome.requires_step_up is True
    assert outcome.halt_reason == "step_up_required"
    assert port.change_calls == []
    assert recorder.records[0].action_taken == "HALT_STEP_UP_REQUIRED"
    assert "ADR-049-D4-biometric-step-up" in recorder.records[0].policies_evaluated


async def test_identity_biometric_disabled_by_mask_config():
    # Config-as-data: a mask may disable identity biometric step-up entirely.
    agent, port, _ = make_agent(mask=make_mask(require_biometric_for_identity=False))
    outcome = await agent.accept_or_decline_identity(
        make_identity_intent(confidence=0.99, biometric_required=True, biometric_verified=False),
        human_reviewed_by="mlro@banxe",
    )
    assert outcome.executed is True
    assert port.change_calls == [("u1", KYCTier.FULL, "corr-1")]


async def test_identity_low_confidence_blocks_and_escalates_mlro():
    agent, port, recorder = make_agent()
    outcome = await agent.accept_or_decline_identity(
        make_identity_intent(confidence=0.50), human_reviewed_by="mlro@banxe"
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "MLRO"
    assert port.change_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert recorder.records[0].escalated_to == "MLRO"


async def test_identity_tier_downgrade_blocked_escalates_mlro_then_raises():
    port = FakeKYCProviderPort(
        change_raises=TierDowngradeBlocked("regulatory hold", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(TierDowngradeBlocked):
        await agent.accept_or_decline_identity(
            make_identity_intent(confidence=0.99, target_tier=KYCTier.BASIC),
            human_reviewed_by="mlro@banxe",
        )
    # Lineage emitted even on provider failure, with MLRO escalation.
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken.startswith("HALT_PROVIDER_ERROR:")
    assert recorder.records[0].compliance_result is ComplianceResult.ESCALATE
    assert recorder.records[0].escalated_to == "MLRO"


# ── BLOCK / scope / process resolution ─────────────────────────────────────────


async def test_block_low_confidence_read():
    agent, port, recorder = make_agent()
    outcome = await agent.check_status(make_status_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.status_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.start_onboarding(make_start_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.start_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright (ADR-049 §D3).
    agent, port, recorder = make_agent(mask=make_mask(scope=("KYCProviderPort.get_status",)))
    outcome = await agent.start_onboarding(make_start_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.start_calls == []
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
    outcome = await agent.start_onboarding(
        make_start_intent(confidence=confidence), human_reviewed_by="mlro@banxe"
    )
    assert outcome.decision is expected


# ── Cost-cap breach ────────────────────────────────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, port, recorder = make_agent()
    intent = make_start_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.start_onboarding(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.start_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.start_onboarding(
        make_start_intent(cost=RequestCost(tokens=200, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.start_calls == []


async def test_window_accumulates_on_successful_action():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.start_onboarding(
        make_start_intent(cost=RequestCost(tokens=300, cost=Decimal("0.02")))
    )
    assert window.used_tokens == 300
    assert window.used_cost == Decimal("0.02")


# ── Compliance gate → MLRO escalation ──────────────────────────────────────────


async def test_compliance_fail_blocks_and_escalates_mlro():
    agent, port, recorder = make_agent()
    outcome = await agent.start_onboarding(
        make_start_intent(), compliance_result=ComplianceResult.FAIL
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "MLRO"
    assert port.start_calls == []
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].escalated_to == "MLRO"


async def test_compliance_escalate_blocks_and_escalates_mlro():
    agent, port, recorder = make_agent()
    outcome = await agent.start_onboarding(
        make_start_intent(), compliance_result=ComplianceResult.ESCALATE
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.start_calls == []
    assert recorder.records[0].compliance_result is ComplianceResult.ESCALATE
    assert recorder.records[0].escalated_to == "MLRO"


# ── Webhook: signature + idempotency + provider error ──────────────────────────


async def test_webhook_processed_emits_lineage():
    agent, port, recorder = make_agent()
    outcome = await agent.handle_provider_webhook(
        {"event": "review.completed"}, "sig-good", correlation_id="corr-wh"
    )

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert port.webhook_calls == [({"event": "review.completed"}, "sig-good")]
    assert recorder.records[0].action_taken == "WEBHOOK_PROCESSED"
    assert recorder.records[0].correlation_id == "corr-wh"
    assert len(recorder.records) == 1


async def test_webhook_idempotent_replay_no_state_change():
    port = FakeKYCProviderPort(webhook=WebhookOutcome(processed=False, deduped=True, user_id="u1"))
    agent, port, recorder = make_agent(port=port)
    outcome = await agent.handle_provider_webhook({"event": "dup"}, "sig-good")

    assert outcome.executed is False  # idempotent replay applied no state change
    assert recorder.records[0].action_taken == "WEBHOOK_DEDUPED"
    assert len(recorder.records) == 1


async def test_webhook_invalid_signature_escalates_and_raises():
    port = FakeKYCProviderPort(
        webhook_raises=InvalidSignature("bad hmac", correlation_id="corr-wh")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(InvalidSignature):
        await agent.handle_provider_webhook({"event": "spoof"}, "sig-bad")

    # Lineage emitted even when the signature is rejected before processing.
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_WEBHOOK_ERROR:InvalidSignature"
    assert recorder.records[0].escalated_to == "MLRO"
    assert recorder.records[0].compliance_result is ComplianceResult.ESCALATE


async def test_webhook_provider_unavailable_records_then_raises():
    port = FakeKYCProviderPort(
        webhook_raises=ProviderUnavailable("provider down", correlation_id="corr-wh")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ProviderUnavailable):
        await agent.handle_provider_webhook({"event": "x"}, "sig")

    assert recorder.records[0].action_taken == "HALT_WEBHOOK_ERROR:ProviderUnavailable"


# ── Window accounting on webhook ───────────────────────────────────────────────


async def test_webhook_window_accumulates_only_when_processed():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.handle_provider_webhook(
        {"e": "1"}, "sig", request_cost=RequestCost(tokens=120, cost=Decimal("0.01"))
    )
    assert window.used_tokens == 120


# ── Lineage obligation (ADR-046) ───────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.start_onboarding(make_start_intent())
    await agent.start_onboarding(make_start_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "kyc_onboarding_agent"
    assert rec.intent == "Start my identity verification"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 400
    assert rec.cost_amount == Decimal("0.04")
    assert rec.budget_window_ref == "kyc_onboarding_agent:default"


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.check_status(make_status_intent(confidence=1.5))
