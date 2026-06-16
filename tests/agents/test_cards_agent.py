"""Tests for the ADR-053 Cards mask agent (services/agents/cards_agent.py).

Covers every Cards-mask path in the §D2 gate-chain order (ADR-053 D4):
the AUTO read path (read_card / read_limits) and its PII-fail BLOCK + DPO
escalation and below-AUTO re-check halt; the protective freeze/block/unfreeze
AUTO-with-cap path, its AML-fail BLOCK + AML escalation and below-AUTO re-check
halt; the money-class issue_card / change_limit REVIEW-bias (forced REVIEW + HITL
hold, then proceed-with-reviewer) with MANDATORY biometric step-up (step-up halt
even at AUTO confidence) and AML-fail BLOCK; cost-cap breach (per-request and
per-window); BLOCK on low confidence; out-of-scope refusal; unresolved
process_ref; the R-SEC/PCI no-secret-in-lineage guarantee; and the
lineage-per-action obligation (ADR-046). The port and the recorder are fakes —
the agent is exercised as pure governance logic with no live infra.
"""

from __future__ import annotations

from decimal import Decimal
import re

import pytest

from services.agents.cards_agent import (
    AgentDecisionRecord,
    AutonomyLevel,
    BlockIntent,
    BudgetBreach,
    CardsAgent,
    CardsMask,
    ChangeLimitIntent,
    ComplianceOverlay,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    FreezeIntent,
    IssueCardIntent,
    ProcessRef,
    ReadCardIntent,
    ReadLimitsIntent,
    RequestCost,
    UnfreezeIntent,
)
from services.card_issuing.card_port import (
    CardLimits,
    CardNetwork,
    CardNotFound,
    CardPort,
    CardStatus,
    CardType,
    CardView,
    IssueCardRequest,
    LimitChange,
    SpendPeriod,
)

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──

# Distinctive masked / opaque values the port returns. They are display-safe
# (PCI-DSS) but must NEVER appear in a lineage record — they ride the outcome
# result only (R-SEC). The no-secret test asserts that separation.
_MASKED_PAN = "**** **** **** 4242"
_PROCESSOR_TOKEN = "PMNTGY-OPAQUE-TOKEN-REF-XYZ"  # nosec B105 — opaque ref, not a credential


def _card_view(card_id: str = "card-1", status: CardStatus = CardStatus.ACTIVE) -> CardView:
    return CardView(
        card_id=card_id,
        status=status,
        masked_pan=_MASKED_PAN,
        network=CardNetwork.MASTERCARD,
        card_type=CardType.VIRTUAL,
        last_four="4242",
        expiry_month=12,
        expiry_year=2030,
        name_on_card="A CUSTOMER",
        processor_token=_PROCESSOR_TOKEN,
    )


def _card_limits(card_id: str = "card-1") -> CardLimits:
    return CardLimits(
        card_id=card_id,
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("500.00"),
        currency="EUR",
    )


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeCardPort(CardPort):
    """In-test CardPort double. Records calls; returns canned masked-only views or
    raises a configured error so the agent's governance logic is exercised without any
    live processor (Paymentology)."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.read_card_calls: list[str] = []
        self.read_limits_calls: list[str] = []
        self.freeze_calls: list[tuple[str, str, str]] = []
        self.block_calls: list[tuple[str, str, str]] = []
        self.unfreeze_calls: list[tuple[str, str]] = []
        self.issue_calls: list[IssueCardRequest] = []
        self.change_limit_calls: list[tuple[str, LimitChange]] = []

    async def read_card(self, card_id: str) -> CardView:
        self.read_card_calls.append(card_id)
        if self._raises is not None:
            raise self._raises
        return _card_view(card_id)

    async def read_limits(self, card_id: str) -> CardLimits:
        self.read_limits_calls.append(card_id)
        if self._raises is not None:
            raise self._raises
        return _card_limits(card_id)

    async def freeze(self, card_id: str, actor: str, reason: str) -> CardView:
        self.freeze_calls.append((card_id, actor, reason))
        if self._raises is not None:
            raise self._raises
        return _card_view(card_id, status=CardStatus.FROZEN)

    async def block(self, card_id: str, actor: str, reason: str) -> CardView:
        self.block_calls.append((card_id, actor, reason))
        if self._raises is not None:
            raise self._raises
        return _card_view(card_id, status=CardStatus.BLOCKED)

    async def unfreeze(self, card_id: str, actor: str) -> CardView:
        self.unfreeze_calls.append((card_id, actor))
        if self._raises is not None:
            raise self._raises
        return _card_view(card_id, status=CardStatus.ACTIVE)

    async def issue_card(self, request: IssueCardRequest) -> CardView:
        self.issue_calls.append(request)
        if self._raises is not None:
            raise self._raises
        return _card_view("card-new")

    async def change_limit(self, card_id: str, new_limits: LimitChange) -> CardLimits:
        self.change_limit_calls.append((card_id, new_limits))
        if self._raises is not None:
            raise self._raises
        return _card_limits(card_id)


# ── Builders ──────────────────────────────────────────────────────────────────


def make_mask(**overrides) -> CardsMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return CardsMask(**base)


def make_agent(
    *,
    mask: CardsMask | None = None,
    port: FakeCardPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[CardsAgent, FakeCardPort, FakeRecorder]:
    port = port or FakeCardPort()
    recorder = recorder or FakeRecorder()
    agent = CardsAgent(
        card_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-CARDS", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_read_card_intent(
    *, confidence: float = 0.99, cost: RequestCost | None = None
) -> ReadCardIntent:
    return ReadCardIntent(
        intent_text="Show me my card",
        process_ref=_ref(),
        card_id="card-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=30, cost=Decimal("0.006")),
    )


def make_read_limits_intent(*, confidence: float = 0.99) -> ReadLimitsIntent:
    return ReadLimitsIntent(
        intent_text="What are my card limits?",
        process_ref=_ref(),
        card_id="card-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=30, cost=Decimal("0.006")),
    )


def make_freeze_intent(
    *, confidence: float = 0.95, cost: RequestCost | None = None, resolved: bool = True
) -> FreezeIntent:
    return FreezeIntent(
        intent_text="Freeze my card, I lost it",
        process_ref=_ref(resolved),
        card_id="card-1",
        actor="user-1",
        reason="card_lost",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=100, cost=Decimal("0.01")),
    )


def make_block_intent(*, confidence: float = 0.95) -> BlockIntent:
    return BlockIntent(
        intent_text="Block my card permanently",
        process_ref=_ref(),
        card_id="card-1",
        actor="user-1",
        reason="card_stolen",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.01")),
    )


def make_unfreeze_intent(*, confidence: float = 0.95) -> UnfreezeIntent:
    return UnfreezeIntent(
        intent_text="Unfreeze my card please",
        process_ref=_ref(),
        card_id="card-1",
        actor="user-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.01")),
    )


def _issue_request() -> IssueCardRequest:
    return IssueCardRequest(
        entity_id="entity-1",
        card_type=CardType.VIRTUAL,
        network=CardNetwork.MASTERCARD,
        currency="EUR",
        name_on_card="A CUSTOMER",
        actor="user-1",
        correlation_id="corr-issue",
    )


def make_issue_intent(
    *,
    confidence: float = 0.99,
    biometric_verified: bool = True,
    cost: RequestCost | None = None,
) -> IssueCardIntent:
    return IssueCardIntent(
        intent_text="Issue me a new virtual card",
        process_ref=_ref(),
        request=_issue_request(),
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=300, cost=Decimal("0.03")),
        biometric_verified=biometric_verified,
    )


def _limit_change() -> LimitChange:
    return LimitChange(
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("2000.00"),
        currency="EUR",
        actor="user-1",
        correlation_id="corr-limit",
    )


def make_change_limit_intent(
    *, confidence: float = 0.99, biometric_verified: bool = True
) -> ChangeLimitIntent:
    return ChangeLimitIntent(
        intent_text="Raise my daily limit to 2000",
        process_ref=_ref(),
        card_id="card-1",
        new_limits=_limit_change(),
        confidence_score=confidence,
        request_cost=RequestCost(tokens=300, cost=Decimal("0.03")),
        biometric_verified=biometric_verified,
    )


# ── Reads: AUTO within cap + PII overlay ──────────────────────────────────────────


async def test_read_card_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.read_card(make_read_card_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.requires_step_up is False
    assert port.read_card_calls == ["card-1"]
    assert outcome.result.masked_pan == _MASKED_PAN
    assert recorder.records[0].action_taken == "READ_CARD"
    assert len(recorder.records) == 1


async def test_read_limits_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.read_limits(make_read_limits_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.read_limits_calls == ["card-1"]
    assert outcome.result.limit_amount == Decimal("500.00")
    assert recorder.records[0].action_taken == "READ_LIMITS"


async def test_read_card_pii_fail_blocks_and_escalates_dpo():
    agent, port, recorder = make_agent()
    outcome = await agent.read_card(
        make_read_card_intent(), compliance_result=ComplianceResult.FAIL
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "DPO"
    assert port.read_card_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].escalated_to == "DPO"


async def test_read_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.read_card(make_read_card_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.read_card_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── Protective freeze / block / unfreeze: AUTO-with-cap ───────────────────────────


async def test_freeze_auto_with_cap_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.freeze(make_freeze_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.requires_step_up is False
    assert port.freeze_calls == [("card-1", "user-1", "card_lost")]
    assert outcome.result.status is CardStatus.FROZEN
    assert recorder.records[0].action_taken == "FREEZE_CARD"


async def test_block_auto_with_cap_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.block(make_block_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.block_calls == [("card-1", "user-1", "card_stolen")]
    assert outcome.result.status is CardStatus.BLOCKED
    assert recorder.records[0].action_taken == "BLOCK_CARD"


async def test_unfreeze_auto_with_cap_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.unfreeze(make_unfreeze_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.unfreeze_calls == [("card-1", "user-1")]
    assert outcome.result.status is CardStatus.ACTIVE
    assert recorder.records[0].action_taken == "UNFREEZE_CARD"


async def test_freeze_no_biometric_step_up_required():
    # A protective freeze is not credit-affecting — it never demands biometric step-up.
    agent, port, _ = make_agent()
    outcome = await agent.freeze(make_freeze_intent(confidence=0.95))
    assert outcome.requires_step_up is False
    assert len(port.freeze_calls) == 1


async def test_freeze_aml_fail_blocks_and_escalates_aml():
    agent, port, recorder = make_agent()
    outcome = await agent.freeze(make_freeze_intent(), compliance_result=ComplianceResult.FAIL)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "AML"
    assert port.freeze_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].escalated_to == "AML"


async def test_protective_below_auto_halts_for_recheck():
    # A protective op below the AUTO band re-checks rather than firing on doubt.
    agent, port, recorder = make_agent()
    outcome = await agent.freeze(make_freeze_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.freeze_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── Money-class issue_card: REVIEW + mandatory biometric step-up ──────────────────


async def test_issue_card_forces_review_hold_even_at_auto_confidence():
    agent, port, recorder = make_agent()
    outcome = await agent.issue_card(make_issue_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert outcome.halt_reason == "hitl_review_required"
    assert port.issue_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-053-D4-money-class-REVIEW" in recorder.records[0].policies_evaluated


async def test_issue_card_with_reviewer_but_no_biometric_halts_step_up():
    # Biometric step-up is MANDATORY even with a reviewer present and at AUTO confidence.
    agent, port, recorder = make_agent()
    outcome = await agent.issue_card(
        make_issue_intent(confidence=0.99, biometric_verified=False),
        human_reviewed_by="ops@banxe",
    )

    assert outcome.executed is False
    assert outcome.requires_step_up is True
    assert outcome.halt_reason == "step_up_required"
    assert port.issue_calls == []
    assert recorder.records[0].action_taken == "HALT_STEP_UP_REQUIRED"
    assert "ADR-049-D4-biometric-step-up" in recorder.records[0].policies_evaluated


async def test_issue_card_proceeds_with_reviewer_and_biometric():
    agent, port, recorder = make_agent()
    outcome = await agent.issue_card(
        make_issue_intent(confidence=0.99, biometric_verified=True),
        human_reviewed_by="ops@banxe",
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert len(port.issue_calls) == 1
    assert outcome.result.card_id == "card-new"
    assert recorder.records[0].action_taken == "ISSUE_CARD"
    assert recorder.records[0].human_reviewed_by == "ops@banxe"
    assert recorder.records[0].correlation_id == "corr-issue"


async def test_issue_card_aml_fail_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.issue_card(
        make_issue_intent(),
        compliance_result=ComplianceResult.FAIL,
        human_reviewed_by="ops@banxe",
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "AML"
    assert port.issue_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


async def test_issue_card_low_confidence_blocks_and_escalates_aml():
    agent, port, recorder = make_agent()
    outcome = await agent.issue_card(
        make_issue_intent(confidence=0.40), human_reviewed_by="ops@banxe"
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "AML"
    assert port.issue_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ── Money-class change_limit: REVIEW + mandatory biometric step-up ────────────────


async def test_change_limit_forces_review_hold():
    agent, port, recorder = make_agent()
    outcome = await agent.change_limit(make_change_limit_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.change_limit_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"


async def test_change_limit_with_reviewer_no_biometric_halts_step_up():
    agent, port, recorder = make_agent()
    outcome = await agent.change_limit(
        make_change_limit_intent(confidence=0.99, biometric_verified=False),
        human_reviewed_by="ops@banxe",
    )

    assert outcome.requires_step_up is True
    assert outcome.halt_reason == "step_up_required"
    assert port.change_limit_calls == []
    assert recorder.records[0].action_taken == "HALT_STEP_UP_REQUIRED"


async def test_change_limit_proceeds_with_reviewer_and_biometric():
    agent, port, recorder = make_agent()
    outcome = await agent.change_limit(
        make_change_limit_intent(confidence=0.99, biometric_verified=True),
        human_reviewed_by="ops@banxe",
    )

    assert outcome.executed is True
    assert len(port.change_limit_calls) == 1
    assert port.change_limit_calls[0][0] == "card-1"
    assert outcome.result.limit_amount == Decimal("500.00")
    assert recorder.records[0].action_taken == "CHANGE_LIMIT"
    assert recorder.records[0].correlation_id == "corr-limit"


# ── Cost-cap breach (per-request AND per-window) ──────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.freeze(
        make_freeze_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.freeze_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.freeze(
        make_freeze_intent(cost=RequestCost(tokens=200, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.freeze_calls == []


async def test_window_accumulates_on_successful_action():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.read_card(make_read_card_intent(cost=RequestCost(tokens=40, cost=Decimal("0.01"))))
    assert window.used_tokens == 40
    assert window.used_cost == Decimal("0.01")


# ── BLOCK / scope / process resolution ────────────────────────────────────────────


async def test_block_low_confidence_protective():
    agent, port, recorder = make_agent()
    outcome = await agent.freeze(make_freeze_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to is None  # protective ops have no HITL escalation route
    assert port.freeze_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.freeze(make_freeze_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.freeze_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright (ADR-053 D4).
    agent, port, recorder = make_agent(mask=make_mask(scope=("CardPort.read_card",)))
    outcome = await agent.freeze(make_freeze_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.freeze_calls == []
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
    # Exercised on a read so the band is observed without the money-class force-REVIEW.
    agent, _, _ = make_agent()
    outcome = await agent.read_card(make_read_card_intent(confidence=confidence))
    assert outcome.decision is expected


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.read_card(make_read_card_intent(confidence=1.5))


# ── Provider error → lineage then re-raise ────────────────────────────────────────


async def test_provider_error_records_then_raises():
    port = FakeCardPort(raises=CardNotFound("no such card", correlation_id="corr-1"))
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(CardNotFound):
        await agent.read_card(make_read_card_intent(confidence=0.99))

    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:CardNotFound"


# ── R-SEC / PCI: no card secret ever reaches the lineage record ───────────────────


async def test_no_card_secret_in_lineage_records():
    # PCI-DSS / R-SEC: the masked_pan / processor_token the port returns ride the
    # outcome RESULT to the caller, but must NEVER appear in any lineage record, and
    # no record field may carry a full PAN-like digit run.
    agent, port, recorder = make_agent()

    # Exercise an executing read and an executing money-class op (the richest paths).
    read = await agent.read_card(make_read_card_intent(confidence=0.99))
    issue = await agent.issue_card(
        make_issue_intent(confidence=0.99, biometric_verified=True),
        human_reviewed_by="ops@banxe",
    )

    # The masked view DID reach the caller via the result (functional return).
    assert read.result.masked_pan == _MASKED_PAN
    assert read.result.processor_token == _PROCESSOR_TOKEN
    assert issue.result.masked_pan == _MASKED_PAN

    pan_run = re.compile(r"\d{13,19}")
    for rec in recorder.records:
        blob = " ".join(
            [
                rec.triggering_event,
                rec.intent,
                rec.reasoning_summary,
                rec.action_taken,
                " ".join(rec.policies_evaluated),
            ]
        )
        assert _MASKED_PAN not in blob
        assert _PROCESSOR_TOKEN not in blob
        assert pan_run.search(blob) is None
        # The record dataclass exposes no card-secret fields at all.
        assert not hasattr(rec, "pan")
        assert not hasattr(rec, "cvv")
        assert not hasattr(rec, "pin")


# ── Lineage obligation (ADR-046) ──────────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.read_card(make_read_card_intent())  # executes
    await agent.freeze(make_freeze_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "cards_agent"
    assert rec.intent == "Show me my card"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 30
    assert rec.cost_amount == Decimal("0.006")
    assert rec.budget_window_ref == "cards_agent:default"


async def test_every_money_class_action_emits_exactly_one_record():
    agent, _, recorder = make_agent()
    await agent.issue_card(make_issue_intent(), human_reviewed_by="ops@banxe")
    assert len(recorder.records) == 1
    await agent.change_limit(make_change_limit_intent(), human_reviewed_by="ops@banxe")
    assert len(recorder.records) == 2


# ── Mask config-as-data ───────────────────────────────────────────────────────────


async def test_mask_is_mixed_with_aml_and_pii_gate():
    mask = make_mask()
    assert mask.autonomy_level is AutonomyLevel.MIXED
    assert mask.compliance_gate == ("AML", "PII")
    assert mask.dpo_role == "DPO"
    assert mask.aml_role == "AML"
    assert mask.require_biometric_for_money_ops is True
    assert "CardPort.freeze" in mask.scope
    assert "CardPort.issue_card" in mask.scope
    assert "CardPort.change_limit" in mask.scope


async def test_custom_escalation_roles_used():
    agent, _, _ = make_agent(mask=make_mask(dpo_role="DataOfficer", aml_role="FinCrime"))
    pii = await agent.read_card(make_read_card_intent(), compliance_result=ComplianceResult.FAIL)
    aml = await agent.freeze(make_freeze_intent(), compliance_result=ComplianceResult.FAIL)
    assert pii.escalated_to == "DataOfficer"
    assert aml.escalated_to == "FinCrime"


async def test_biometric_can_be_disabled_by_mask():
    # config-as-data: a mask that disables money-op step-up lets a reviewed issue proceed
    # with no biometric verification (the toggle governs the step-up gate).
    agent, port, _ = make_agent(mask=make_mask(require_biometric_for_money_ops=False))
    outcome = await agent.issue_card(
        make_issue_intent(confidence=0.99, biometric_verified=False),
        human_reviewed_by="ops@banxe",
    )
    assert outcome.executed is True
    assert len(port.issue_calls) == 1


async def test_compliance_overlay_routing_values():
    assert ComplianceOverlay.PII.value == "PII"
    assert ComplianceOverlay.AML.value == "AML"
