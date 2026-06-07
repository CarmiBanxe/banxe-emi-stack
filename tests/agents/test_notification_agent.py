"""Tests for the ADR-049 Notifications mask agent
(services/agents/notification_agent.py).

Covers every mask path in the §D2 gate-chain order:
AUTO informational send, the funds-data override → forced REVIEW HITL hold then
proceed-with-reviewer (regardless of confidence), PII-gate fail → BLOCK + DPO
escalation, cost-cap breach (per-request and per-window), the AUTO channel-read
(check_channel) and its below-AUTO re-check halt, BLOCK on low confidence,
out-of-scope refusal, unresolved process_ref, provider-error lineage, and the
lineage-per-action obligation (ADR-046). The port and the recorder are fakes —
the agent is exercised as pure governance logic with no live infra.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.notification_agent import (
    AgentDecisionRecord,
    AutonomyLevel,
    BudgetBreach,
    ChannelCheckIntent,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    NotificationAgent,
    NotificationMask,
    NotificationSendIntent,
    ProcessRef,
    RequestCost,
)
from services.notifications.notification_provider_port import (
    DeliveryResult,
    NotificationChannel,
    NotificationMessage,
    NotificationProviderPort,
    Recipient,
    Severity,
    ValidationError,
)

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeNotificationProviderPort(NotificationProviderPort):
    """In-test NotificationProviderPort double. Records calls; returns canned
    results or raises a configured error so the agent's governance logic is
    exercised without any live provider."""

    def __init__(
        self,
        *,
        send_result: list[DeliveryResult] | None = None,
        available: bool = True,
        send_raises: Exception | None = None,
    ) -> None:
        self._send_result = send_result or [
            DeliveryResult(
                channel=NotificationChannel.EMAIL,
                delivered=True,
                deduped=False,
                provider_message_id="msg-1",
            )
        ]
        self._available = available
        self._send_raises = send_raises
        self.send_calls: list[tuple[Recipient, NotificationMessage]] = []
        self.available_calls: list[NotificationChannel] = []

    async def send(
        self, recipient: Recipient, message: NotificationMessage
    ) -> list[DeliveryResult]:
        self.send_calls.append((recipient, message))
        if self._send_raises is not None:
            raise self._send_raises
        return self._send_result

    async def is_channel_available(self, channel: NotificationChannel) -> bool:
        self.available_calls.append(channel)
        return self._available


# ── Builders ──────────────────────────────────────────────────────────────────


def make_mask(**overrides) -> NotificationMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return NotificationMask(**base)


def make_agent(
    *,
    mask: NotificationMask | None = None,
    port: FakeNotificationProviderPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[NotificationAgent, FakeNotificationProviderPort, FakeRecorder]:
    port = port or FakeNotificationProviderPort()
    recorder = recorder or FakeRecorder()
    agent = NotificationAgent(
        provider_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-NOTIFY", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def _recipient() -> Recipient:
    return Recipient(user_id="u1", channel_preferences=[NotificationChannel.EMAIL])


def _message(severity: Severity = Severity.INFO) -> NotificationMessage:
    return NotificationMessage(
        severity=severity,
        subject="Your weekly summary",
        body="Here is an update for you.",
        correlation_id="corr-1",
        dedupe_key="dk-1",
    )


def make_send_intent(
    *,
    confidence: float = 0.95,
    cost: RequestCost | None = None,
    resolved: bool = True,
    contains_funds_data: bool = False,
    severity: Severity = Severity.INFO,
) -> NotificationSendIntent:
    return NotificationSendIntent(
        intent_text="Send my account notification",
        process_ref=_ref(resolved),
        recipient=_recipient(),
        message=_message(severity),
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=200, cost=Decimal("0.02")),
        contains_funds_data=contains_funds_data,
    )


def make_channel_intent(
    *, confidence: float = 0.99, channel: NotificationChannel = NotificationChannel.EMAIL
) -> ChannelCheckIntent:
    return ChannelCheckIntent(
        intent_text="Is email delivery available?",
        process_ref=_ref(),
        channel=channel,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=20, cost=Decimal("0.005")),
    )


# ── AUTO informational send ─────────────────────────────────────────────────────


async def test_auto_informational_send_executes_no_hitl():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(make_send_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.requires_step_up is False
    assert len(port.send_calls) == 1
    assert recorder.records[0].action_taken == "SEND_NOTIFICATION"
    assert len(recorder.records) == 1


async def test_send_result_surfaced_on_outcome():
    port = FakeNotificationProviderPort(
        send_result=[
            DeliveryResult(
                channel=NotificationChannel.SMS,
                delivered=True,
                deduped=False,
                provider_message_id="m9",
            )
        ]
    )
    agent, port, _ = make_agent(port=port)
    outcome = await agent.send_notification(make_send_intent())
    assert isinstance(outcome.result, list)
    assert outcome.result[0].channel is NotificationChannel.SMS


# ── Funds-data override: forced REVIEW regardless of confidence ──────────────────


async def test_funds_data_forces_review_hold_even_at_auto_confidence():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(
        make_send_intent(confidence=0.99, contains_funds_data=True)
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert outcome.halt_reason == "hitl_review_required"
    assert port.send_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert recorder.records[0].human_reviewed_by is None
    assert "ADR-049-D3-funds-data-REVIEW" in recorder.records[0].policies_evaluated


async def test_funds_data_proceeds_with_reviewer():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(
        make_send_intent(confidence=0.99, contains_funds_data=True),
        human_reviewed_by="ops@banxe",
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert len(port.send_calls) == 1
    assert recorder.records[0].action_taken == "SEND_NOTIFICATION"
    assert recorder.records[0].human_reviewed_by == "ops@banxe"


async def test_non_funds_data_review_band_holds_for_hitl():
    # A plain informational send in the REVIEW band still holds for HITL.
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(make_send_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.send_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-049-D3-funds-data-REVIEW" not in recorder.records[0].policies_evaluated


async def test_review_band_with_reviewer_proceeds():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(
        make_send_intent(confidence=0.80), human_reviewed_by="ops@banxe"
    )
    assert outcome.executed is True
    assert recorder.records[0].action_taken == "SEND_NOTIFICATION"
    assert recorder.records[0].human_reviewed_by == "ops@banxe"


# ── PII overlay (ADR-016) compliance gate ────────────────────────────────────────


async def test_pii_fail_blocks_and_escalates_dpo():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(
        make_send_intent(), compliance_result=ComplianceResult.FAIL
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "DPO"
    assert port.send_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].escalated_to == "DPO"


async def test_pii_escalate_blocks_and_escalates_dpo():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(
        make_send_intent(), compliance_result=ComplianceResult.ESCALATE
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.send_calls == []
    assert recorder.records[0].escalated_to == "DPO"


# ── check_channel: AUTO read + below-AUTO re-check ───────────────────────────────


async def test_check_channel_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.check_channel(make_channel_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert port.available_calls == [NotificationChannel.EMAIL]
    assert outcome.result is True
    assert recorder.records[0].action_taken == "CHECK_CHANNEL_AVAILABLE"
    assert len(recorder.records) == 1


async def test_check_channel_below_auto_halts_for_recheck():
    # Reads are AUTO-only: a below-AUTO read halts (re-check), not a HITL hold.
    agent, port, recorder = make_agent()
    outcome = await agent.check_channel(make_channel_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.available_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_check_channel_unavailable_returns_false_result():
    port = FakeNotificationProviderPort(available=False)
    agent, port, _ = make_agent(port=port)
    outcome = await agent.check_channel(make_channel_intent(confidence=0.99))
    assert outcome.executed is True
    assert outcome.result is False


# ── BLOCK / scope / process resolution ───────────────────────────────────────────


async def test_block_low_confidence_send():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(make_send_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.send_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_read():
    agent, port, recorder = make_agent()
    outcome = await agent.check_channel(make_channel_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.available_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.send_notification(make_send_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.send_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright (ADR-049 §D3).
    agent, port, recorder = make_agent(
        mask=make_mask(scope=("NotificationProviderPort.is_channel_available",))
    )
    outcome = await agent.send_notification(make_send_intent(confidence=0.95))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.send_calls == []
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
    outcome = await agent.send_notification(
        make_send_intent(confidence=confidence), human_reviewed_by="ops@banxe"
    )
    assert outcome.decision is expected


# ── Cost-cap breach ──────────────────────────────────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, port, recorder = make_agent()
    intent = make_send_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.send_notification(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.send_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.send_notification(
        make_send_intent(cost=RequestCost(tokens=200, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.send_calls == []


async def test_window_accumulates_on_successful_send():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.send_notification(
        make_send_intent(cost=RequestCost(tokens=300, cost=Decimal("0.02")))
    )
    assert window.used_tokens == 300
    assert window.used_cost == Decimal("0.02")


# ── Provider error → lineage then re-raise ───────────────────────────────────────


async def test_provider_validation_error_records_then_raises():
    port = FakeNotificationProviderPort(
        send_raises=ValidationError("empty body", correlation_id="corr-1", dedupe_key="dk-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ValidationError):
        await agent.send_notification(make_send_intent(confidence=0.95))

    # Lineage emitted even when the provider rejects the send.
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:ValidationError"


# ── Lineage obligation (ADR-046) ─────────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.send_notification(make_send_intent())
    await agent.send_notification(make_send_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "notification_agent"
    assert rec.intent == "Send my account notification"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 200
    assert rec.cost_amount == Decimal("0.02")
    assert rec.budget_window_ref == "notification_agent:default"


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.send_notification(make_send_intent(confidence=1.5))


# ── Mask config-as-data ──────────────────────────────────────────────────────────


async def test_mask_is_auto_biased_with_pii_gate():
    mask = make_mask()
    assert mask.autonomy_level is AutonomyLevel.AUTO_BIASED
    assert mask.compliance_gate == ("PII",)
    assert mask.dpo_role == "DPO"
    assert "NotificationProviderPort.send" in mask.scope


async def test_custom_dpo_role_used_on_pii_block():
    agent, _, recorder = make_agent(mask=make_mask(dpo_role="DataOfficer"))
    outcome = await agent.send_notification(
        make_send_intent(), compliance_result=ComplianceResult.FAIL
    )
    assert outcome.escalated_to == "DataOfficer"
    assert recorder.records[0].escalated_to == "DataOfficer"
