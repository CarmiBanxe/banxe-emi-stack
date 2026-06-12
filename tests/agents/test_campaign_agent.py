"""Tests for the ORG §2.8.2 / COBS 4 campaign mask agent
(services/agents/campaign_agent.py).

Covers every mask path in the §D2 gate-chain order: draft AUTO/REVIEW happy paths
(prepare_campaign), the AUTO read (list_campaigns), and — the headline regulatory
invariant — the MANDATORY MLRO STEP-UP ON PUBLISH (COBS 4): a financial-promotion
publish can NEVER be autonomous, so at confidence=1.0 with no MLRO token it HALTS,
the domain publish is NEVER called, and it escalates to the MLRO; with a valid
token it proceeds. Plus HALT_UNRESOLVED_PROCESS, REJECT_OUT_OF_SCOPE,
HALT_REVIEW_DEFERRED, BLOCK_LOW_CONFIDENCE, HALT_COST_CAP_BREACH (per-request and
per-window), HALT_COMPLIANCE_BLOCK (→MLRO), HALT_PROVIDER_ERROR (emit + reraise),
invalid-confidence ValueError, R-SEC (no content/PII in lineage), and the
one-record-per-action obligation (ADR-046). The port and recorder are fakes — the
agent is exercised as pure governance logic with no live infra.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.campaign_agent import (
    AgentDecisionRecord,
    BudgetBreach,
    CampaignAgent,
    CampaignMask,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    ListCampaignsIntent,
    PrepareCampaignIntent,
    ProcessRef,
    PublishCampaignIntent,
    RequestCost,
)
from services.campaign.campaign_port import (
    CampaignChannel,
    CampaignDraft,
    CampaignPort,
    CampaignStatus,
    MlroReviewToken,
    ProviderUnavailable,
    PublishedCampaign,
)

# ── Fakes (port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeCampaignPort(CampaignPort):
    """In-test CampaignPort double. Records calls; returns canned results or raises a
    configured error so the agent's governance logic is exercised without live infra."""

    def __init__(self, *, publish_raises: Exception | None = None) -> None:
        self._publish_raises = publish_raises
        self.prepare_calls: list[CampaignDraft] = []
        self.publish_calls: list[tuple[CampaignDraft, MlroReviewToken]] = []
        self.list_calls: int = 0

    async def prepare_campaign(self, draft: CampaignDraft) -> CampaignDraft:
        self.prepare_calls.append(draft)
        return draft

    async def publish_campaign(
        self, draft: CampaignDraft, mlro_token: MlroReviewToken
    ) -> PublishedCampaign:
        self.publish_calls.append((draft, mlro_token))
        if self._publish_raises is not None:
            raise self._publish_raises
        return PublishedCampaign(
            campaign_id=draft.campaign_id,
            status=CampaignStatus.PUBLISHED,
            channel=draft.channel,
            recipients=draft.estimated_reach,
            reviewed_by=mlro_token.reviewed_by,
        )

    async def list_campaigns(self) -> tuple[CampaignDraft, ...]:
        self.list_calls += 1
        return ()


# ── Builders ────────────────────────────────────────────────────────────────────

SECRET_BODY = "VIP-ONLY token abc123 — Earn 7% AER, john@example.com"
SECRET_SUBJECT = "Your exclusive 7% offer"


def make_mask(**overrides) -> CampaignMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return CampaignMask(**base)


def make_agent(
    *,
    mask: CampaignMask | None = None,
    port: FakeCampaignPort | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[CampaignAgent, FakeCampaignPort, FakeRecorder]:
    port = port or FakeCampaignPort()
    recorder = FakeRecorder()
    agent = CampaignAgent(
        campaign_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return ProcessRef("PROC-CAMPAIGN", "1") if resolved else ProcessRef("", "")


def make_draft(*, financial: bool = True, reach: int = 1000) -> CampaignDraft:
    return CampaignDraft(
        campaign_id="camp-1",
        name="Summer Savings Boost",
        segment="active-uk",
        channel=CampaignChannel.EMAIL,
        subject=SECRET_SUBJECT,
        body=SECRET_BODY,
        is_financial_promotion=financial,
        estimated_reach=reach,
        budget=Decimal("250.00"),
    )


def make_prepare_intent(
    *, confidence: float = 0.95, cost: RequestCost | None = None, resolved: bool = True
) -> PrepareCampaignIntent:
    return PrepareCampaignIntent(
        intent_text="Draft a summer savings campaign",
        process_ref=_ref(resolved),
        draft=make_draft(),
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=400, cost=Decimal("0.04")),
    )


def make_publish_intent(
    *, confidence: float = 1.0, financial: bool = True, cost: RequestCost | None = None
) -> PublishCampaignIntent:
    return PublishCampaignIntent(
        intent_text="Publish the summer savings campaign",
        process_ref=_ref(),
        draft=make_draft(financial=financial),
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=600, cost=Decimal("0.06")),
    )


def make_list_intent(*, confidence: float = 0.99) -> ListCampaignsIntent:
    return ListCampaignsIntent(
        intent_text="List campaigns",
        process_ref=_ref(),
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.01")),
    )


def valid_token() -> MlroReviewToken:
    return MlroReviewToken(token_id="tok-1", campaign_id="camp-1", reviewed_by="mlro@banxe")


# ── Draft (prepare): free, REVIEW-biased ─────────────────────────────────────────


async def test_prepare_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.prepare_campaign(make_prepare_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_step_up is False
    assert port.prepare_calls and port.prepare_calls[0].campaign_id == "camp-1"
    assert recorder.records[0].action_taken == "PREPARE_CAMPAIGN"
    assert len(recorder.records) == 1


async def test_prepare_review_band_holds_for_hitl():
    agent, port, recorder = make_agent()
    outcome = await agent.prepare_campaign(make_prepare_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.prepare_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"


async def test_prepare_review_with_reviewer_proceeds():
    agent, port, recorder = make_agent()
    outcome = await agent.prepare_campaign(
        make_prepare_intent(confidence=0.80), human_reviewed_by="head-marketing@banxe"
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert port.prepare_calls and port.prepare_calls[0].campaign_id == "camp-1"
    assert recorder.records[0].human_reviewed_by == "head-marketing@banxe"
    assert recorder.records[0].action_taken == "PREPARE_CAMPAIGN"


# ── THE COBS 4 INVARIANT: mandatory MLRO step-up on financial-promo publish ──────


async def test_publish_financial_promo_without_token_halts_and_escalates_mlro():
    # The headline invariant: publish @ confidence=1.0 with NO MLRO token can NEVER
    # be autonomous — it HALTS, the domain publish is never called, escalates → MLRO.
    agent, port, recorder = make_agent()
    outcome = await agent.publish_campaign(make_publish_intent(confidence=1.0), mlro_token=None)

    assert outcome.executed is False
    assert outcome.decision is ConfirmationDecision.AUTO  # max confidence still HALTS
    assert outcome.requires_step_up is True
    assert outcome.halt_reason == "mlro_review_required"
    assert outcome.escalated_to == "MLRO"
    assert port.publish_calls == []  # domain publish NEVER called
    assert recorder.records[0].action_taken == "HALT_MLRO_REVIEW_REQUIRED"
    assert recorder.records[0].escalated_to == "MLRO"
    assert "COBS4-MLRO-publish-step-up" in recorder.records[0].policies_evaluated


async def test_publish_with_invalid_token_halts():
    # A token bound to another campaign is not valid sign-off — still HALTS.
    agent, port, recorder = make_agent()
    wrong = MlroReviewToken(token_id="tok-x", campaign_id="other", reviewed_by="mlro@banxe")
    outcome = await agent.publish_campaign(make_publish_intent(confidence=0.99), mlro_token=wrong)

    assert outcome.executed is False
    assert outcome.halt_reason == "mlro_review_required"
    assert port.publish_calls == []


async def test_publish_with_valid_token_proceeds():
    agent, port, recorder = make_agent()
    outcome = await agent.publish_campaign(
        make_publish_intent(confidence=0.99), mlro_token=valid_token()
    )

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert len(port.publish_calls) == 1
    sent_draft, sent_token = port.publish_calls[0]
    assert sent_draft.campaign_id == "camp-1"
    assert sent_token.reviewed_by == "mlro@banxe"
    assert isinstance(outcome.result, PublishedCampaign)
    assert recorder.records[0].action_taken == "PUBLISH_CAMPAIGN"
    assert recorder.records[0].human_reviewed_by == "mlro@banxe"


async def test_publish_financial_promo_requires_token_even_if_mask_disables_it():
    # COBS 4 is a hard floor: a financial promotion ALWAYS needs MLRO sign-off, even
    # when the mask flag would waive it for ordinary publishes.
    agent, port, recorder = make_agent(mask=make_mask(require_mlro_for_publish=False))
    outcome = await agent.publish_campaign(
        make_publish_intent(confidence=1.0, financial=True), mlro_token=None
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "mlro_review_required"
    assert port.publish_calls == []


async def test_publish_non_financial_still_gated_by_mask_default():
    # Default mask requires a token on EVERY publish (require_mlro_for_publish=True).
    agent, port, _ = make_agent()
    outcome = await agent.publish_campaign(
        make_publish_intent(confidence=1.0, financial=False), mlro_token=None
    )
    assert outcome.executed is False
    assert outcome.halt_reason == "mlro_review_required"
    assert port.publish_calls == []


async def test_publish_low_confidence_blocks_and_escalates_mlro():
    agent, port, recorder = make_agent()
    outcome = await agent.publish_campaign(
        make_publish_intent(confidence=0.50), mlro_token=valid_token()
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "MLRO"
    assert port.publish_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert recorder.records[0].escalated_to == "MLRO"


# ── AUTO read (list_campaigns) ───────────────────────────────────────────────────


async def test_list_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.list_campaigns(make_list_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.list_calls == 1
    assert recorder.records[0].action_taken == "LIST_CAMPAIGNS"


async def test_list_below_auto_band_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.list_campaigns(make_list_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.list_calls == 0
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── BLOCK / scope / process resolution ───────────────────────────────────────────


async def test_block_low_confidence_prepare():
    agent, port, recorder = make_agent()
    outcome = await agent.prepare_campaign(make_prepare_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to is None  # prepare is not a publish — no MLRO escalation
    assert port.prepare_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.prepare_campaign(make_prepare_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.prepare_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    agent, port, recorder = make_agent(mask=make_mask(scope=("CampaignPort.list_campaigns",)))
    outcome = await agent.prepare_campaign(make_prepare_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.prepare_calls == []
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
    outcome = await agent.prepare_campaign(
        make_prepare_intent(confidence=confidence), human_reviewed_by="head-marketing@banxe"
    )
    assert outcome.decision is expected


# ── Cost-cap breach ──────────────────────────────────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, port, recorder = make_agent()
    intent = make_prepare_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.prepare_campaign(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.prepare_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.prepare_campaign(
        make_prepare_intent(cost=RequestCost(tokens=200, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.prepare_calls == []


async def test_window_accumulates_on_successful_action():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.prepare_campaign(
        make_prepare_intent(cost=RequestCost(tokens=300, cost=Decimal("0.02")))
    )
    assert window.used_tokens == 300
    assert window.used_cost == Decimal("0.02")


# ── Compliance gate → MLRO escalation ────────────────────────────────────────────


async def test_compliance_fail_blocks_and_escalates_mlro():
    agent, port, recorder = make_agent()
    outcome = await agent.prepare_campaign(
        make_prepare_intent(), compliance_result=ComplianceResult.FAIL
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "MLRO"
    assert port.prepare_calls == []
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


# ── Provider error: emit + reraise ───────────────────────────────────────────────


async def test_publish_provider_error_records_then_raises():
    port = FakeCampaignPort(
        publish_raises=ProviderUnavailable("engine down", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ProviderUnavailable):
        await agent.publish_campaign(make_publish_intent(confidence=0.99), mlro_token=valid_token())

    # Lineage emitted even on provider failure (executed=False).
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:ProviderUnavailable"


# ── R-SEC: no marketing content or PII in lineage ────────────────────────────────


async def test_rsec_no_content_or_pii_in_lineage():
    agent, _, recorder = make_agent()
    await agent.publish_campaign(make_publish_intent(confidence=1.0), mlro_token=None)
    rec = recorder.records[0]
    serialized = " ".join(
        str(v)
        for v in (
            rec.triggering_event,
            rec.intent,
            rec.reasoning_summary,
            *rec.policies_evaluated,
        )
    )
    # The campaign body/subject (marketing content + embedded PII) never appears.
    assert SECRET_BODY not in serialized
    assert SECRET_SUBJECT not in serialized
    assert "john@example.com" not in serialized
    # Opaque handles ARE present (campaign_id / segment).
    assert "camp-1" in rec.triggering_event
    assert "active-uk" in rec.triggering_event


# ── Lineage obligation (ADR-046) ─────────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.prepare_campaign(make_prepare_intent())
    await agent.prepare_campaign(make_prepare_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "campaign_agent"
    assert rec.intent == "Draft a summer savings campaign"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 400
    assert rec.cost_amount == Decimal("0.04")
    assert rec.budget_window_ref == "campaign_agent:default"


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.list_campaigns(make_list_intent(confidence=1.5))
