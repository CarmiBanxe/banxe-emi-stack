"""Tests for the ADR-055 Statements mask agent
(services/agents/statement_agent.py — the client-facing StatementClientAgent).

Covers every mask path in the §D2 gate-chain order: AUTO reads (get_statement,
list_statements) and AUTO-with-cap generate_statement, plus their PII-fail → BLOCK + DPO
escalation; the below-AUTO read/generate re-check halt; deliver_statement IN_APP AUTO, the
external-channel (EMAIL / EXPORT) data-egress override → forced REVIEW HITL hold then
proceed-with-reviewer (regardless of confidence), the port data-egress guard
DeliveryEgressBlocked → recorded-then-raised, the egress-compliance fail → BLOCK + egress
escalation; cost-cap breach (per-request token-heavy generation AND per-window); BLOCK on low
confidence; unresolved process_ref; out-of-scope refusal; the no-raw-PII-in-lineage R-SEC
guarantee; and the lineage-per-action obligation (ADR-046). The port and the recorder are
fakes — the agent is exercised as pure governance logic with no live infra and NO dependency
on the domain client_statements implementation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.statement_agent import (
    AgentDecisionRecord,
    AutonomyLevel,
    BudgetBreach,
    ComplianceOverlay,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    DeliverStatementIntent,
    GenerateStatementIntent,
    GetStatementIntent,
    ListStatementsIntent,
    ProcessRef,
    RequestCost,
    StatementClientAgent,
    StatementMask,
)
from services.client_statements.statement_port import (
    ComplianceBlock,
    DeliveryChannel,
    DeliveryEgressBlocked,
    DeliveryResult,
    DeliveryStatus,
    GenerateStatementRequest,
    StatementDescriptor,
    StatementFormat,
    StatementNotFound,
    StatementPeriod,
    StatementPort,
    StatementView,
)

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeStatementPort(StatementPort):
    """In-test StatementPort double. Records calls; returns canned read-only / generated
    results or raises a configured StatementPortError so the agent's governance logic is
    exercised without any live client_statements adapter."""

    def __init__(
        self,
        *,
        view: StatementView | None = None,
        listing: list[StatementDescriptor] | None = None,
        generated: StatementView | None = None,
        delivery_result: DeliveryResult | None = None,
        get_raises: Exception | None = None,
        generate_raises: Exception | None = None,
        deliver_raises: Exception | None = None,
    ) -> None:
        self._view = view or StatementView(
            statement_id="stmt-1",
            entity_id="ent-1",
            period=StatementPeriod.MONTH,
            opening_balance=Decimal("100.00"),
            closing_balance=Decimal("250.00"),
            line_count=12,
            currency="EUR",
            format=StatementFormat.PDF,
        )
        self._listing = (
            listing
            if listing is not None
            else [
                StatementDescriptor(
                    statement_id="stmt-1",
                    period=StatementPeriod.MONTH,
                    currency="EUR",
                    format=StatementFormat.PDF,
                )
            ]
        )
        self._generated = generated or self._view
        self._delivery_result = delivery_result or DeliveryResult(
            statement_id="stmt-1",
            channel=DeliveryChannel.IN_APP,
            status=DeliveryStatus.DELIVERED,
        )
        self._get_raises = get_raises
        self._generate_raises = generate_raises
        self._deliver_raises = deliver_raises
        self.get_calls: list[str] = []
        self.list_calls: list[tuple[str, StatementPeriod]] = []
        self.generate_calls: list[GenerateStatementRequest] = []
        self.deliver_calls: list[tuple[str, DeliveryChannel]] = []

    async def get_statement(self, statement_id: str) -> StatementView:
        self.get_calls.append(statement_id)
        if self._get_raises is not None:
            raise self._get_raises
        return self._view

    async def list_statements(
        self, entity_id: str, period: StatementPeriod
    ) -> list[StatementDescriptor]:
        self.list_calls.append((entity_id, period))
        return self._listing

    async def generate_statement(self, request: GenerateStatementRequest) -> StatementView:
        self.generate_calls.append(request)
        if self._generate_raises is not None:
            raise self._generate_raises
        return self._generated

    async def deliver_statement(
        self, statement_id: str, channel: DeliveryChannel
    ) -> DeliveryResult:
        self.deliver_calls.append((statement_id, channel))
        if self._deliver_raises is not None:
            raise self._deliver_raises
        return self._delivery_result


# ── Builders ──────────────────────────────────────────────────────────────────


def make_mask(**overrides) -> StatementMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=50_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=500_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return StatementMask(**base)


def make_agent(
    *,
    mask: StatementMask | None = None,
    port: FakeStatementPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[StatementClientAgent, FakeStatementPort, FakeRecorder]:
    port = port or FakeStatementPort()
    recorder = recorder or FakeRecorder()
    agent = StatementClientAgent(
        statement_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-STATEMENTS", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_get_intent(
    *, confidence: float = 0.99, cost: RequestCost | None = None, resolved: bool = True
) -> GetStatementIntent:
    return GetStatementIntent(
        intent_text="Show my March statement",
        process_ref=_ref(resolved),
        statement_id="stmt-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=800, cost=Decimal("0.02")),
    )


def make_list_intent(*, confidence: float = 0.99) -> ListStatementsIntent:
    return ListStatementsIntent(
        intent_text="List my statements this year",
        process_ref=_ref(),
        entity_id="ent-1",
        period=StatementPeriod.YEAR,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=500, cost=Decimal("0.01")),
    )


def make_generate_intent(
    *, confidence: float = 0.99, cost: RequestCost | None = None
) -> GenerateStatementIntent:
    return GenerateStatementIntent(
        intent_text="Generate my Q1 statement",
        process_ref=_ref(),
        entity_id="ent-1",
        period=StatementPeriod.QUARTER,
        format=StatementFormat.PDF,
        actor="user-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=12_000, cost=Decimal("0.20")),
    )


def make_deliver_intent(
    *,
    confidence: float = 0.99,
    channel: DeliveryChannel = DeliveryChannel.IN_APP,
    cost: RequestCost | None = None,
) -> DeliverStatementIntent:
    return DeliverStatementIntent(
        intent_text="Deliver my March statement",
        process_ref=_ref(),
        statement_id="stmt-1",
        channel=channel,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=1_000, cost=Decimal("0.02")),
    )


# ── AUTO reads + generate ───────────────────────────────────────────────────────


async def test_get_statement_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.get_statement(make_get_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.requires_step_up is False
    assert port.get_calls == ["stmt-1"]
    assert outcome.result.closing_balance == Decimal("250.00")
    assert recorder.records[0].action_taken == "GET_STATEMENT"
    assert len(recorder.records) == 1


async def test_list_statements_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.list_statements(make_list_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.list_calls == [("ent-1", StatementPeriod.YEAR)]
    assert outcome.result[0].statement_id == "stmt-1"
    assert recorder.records[0].action_taken == "LIST_STATEMENTS"


async def test_generate_statement_auto_with_cap_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.generate_statement(make_generate_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_step_up is False  # NO biometric — generation is not money movement
    assert len(port.generate_calls) == 1
    assert port.generate_calls[0].period is StatementPeriod.QUARTER
    assert outcome.result.statement_id == "stmt-1"
    assert recorder.records[0].action_taken == "GENERATE_STATEMENT"


# ── PII overlay (ADR-016) on reads / generate → BLOCK + DPO ───────────────────


async def test_get_statement_pii_fail_blocks_and_escalates_dpo():
    agent, port, recorder = make_agent()
    outcome = await agent.get_statement(make_get_intent(), compliance_result=ComplianceResult.FAIL)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "DPO"
    assert port.get_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].escalated_to == "DPO"


async def test_generate_statement_pii_fail_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.generate_statement(
        make_generate_intent(), compliance_result=ComplianceResult.ESCALATE
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.escalated_to == "DPO"
    assert port.generate_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


# ── below-AUTO read / generate re-check halt ──────────────────────────────────


async def test_get_statement_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.get_statement(make_get_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.get_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_generate_statement_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.generate_statement(make_generate_intent(confidence=0.85))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"
    assert port.generate_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── deliver_statement: IN_APP AUTO, external REVIEW, egress guards ─────────────


async def test_deliver_in_app_auto_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.deliver_statement(
        make_deliver_intent(confidence=0.99, channel=DeliveryChannel.IN_APP)
    )

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_step_up is False
    assert port.deliver_calls == [("stmt-1", DeliveryChannel.IN_APP)]
    assert outcome.result.status is DeliveryStatus.DELIVERED
    assert recorder.records[0].action_taken == "DELIVER_STATEMENT"


@pytest.mark.parametrize("channel", [DeliveryChannel.EMAIL, DeliveryChannel.EXPORT])
async def test_deliver_external_forces_review_hold_even_at_auto_confidence(channel):
    agent, port, recorder = make_agent()
    outcome = await agent.deliver_statement(make_deliver_intent(confidence=0.99, channel=channel))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert outcome.requires_step_up is False  # NO biometric — data-egress, not money movement
    assert outcome.halt_reason == "hitl_review_required"
    assert port.deliver_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert recorder.records[0].human_reviewed_by is None
    assert "ADR-055-data-egress-REVIEW" in recorder.records[0].policies_evaluated


@pytest.mark.parametrize("channel", [DeliveryChannel.EMAIL, DeliveryChannel.EXPORT])
async def test_deliver_external_proceeds_with_reviewer(channel):
    port = FakeStatementPort(
        delivery_result=DeliveryResult(
            statement_id="stmt-1", channel=channel, status=DeliveryStatus.DELIVERED
        )
    )
    agent, port, recorder = make_agent(port=port)
    outcome = await agent.deliver_statement(
        make_deliver_intent(confidence=0.99, channel=channel),
        human_reviewed_by="dpo@banxe",
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert port.deliver_calls == [("stmt-1", channel)]
    assert recorder.records[0].action_taken == "DELIVER_STATEMENT"
    assert recorder.records[0].human_reviewed_by == "dpo@banxe"


async def test_deliver_in_app_low_confidence_review_band_holds_for_hitl():
    # An in-boundary delivery in the REVIEW band still holds for HITL (delivery supports it),
    # but NOT via the data-egress override.
    agent, port, recorder = make_agent()
    outcome = await agent.deliver_statement(
        make_deliver_intent(confidence=0.80, channel=DeliveryChannel.IN_APP)
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.deliver_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-055-data-egress-REVIEW" not in recorder.records[0].policies_evaluated


async def test_deliver_egress_blocked_records_then_raises():
    # Port data-egress guard fires (defense-in-depth): lineage emitted then re-raised.
    port = FakeStatementPort(
        deliver_raises=DeliveryEgressBlocked("egress forbidden", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(DeliveryEgressBlocked):
        await agent.deliver_statement(
            make_deliver_intent(confidence=0.99, channel=DeliveryChannel.EMAIL),
            human_reviewed_by="dpo@banxe",
        )

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "HALT_PROVIDER_ERROR:DeliveryEgressBlocked"
    assert rec.human_reviewed_by == "dpo@banxe"
    # The blocked delivery must NOT count against the window (executed=False).


async def test_deliver_egress_compliance_fail_blocks_and_escalates_egress():
    agent, port, recorder = make_agent(mask=make_mask(egress_role="ComplianceEgress"))
    outcome = await agent.deliver_statement(
        make_deliver_intent(confidence=0.99, channel=DeliveryChannel.EMAIL),
        compliance_result=ComplianceResult.FAIL,
        human_reviewed_by="dpo@banxe",
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "ComplianceEgress"
    assert port.deliver_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL


async def test_deliver_port_compliance_block_records_then_raises():
    port = FakeStatementPort(
        deliver_raises=ComplianceBlock("PII overlay forbade un-redacted egress", correlation_id="c")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ComplianceBlock):
        await agent.deliver_statement(
            make_deliver_intent(confidence=0.99, channel=DeliveryChannel.IN_APP)
        )
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:ComplianceBlock"


# ── get_statement unknown → StatementNotFound recorded then raised ─────────────


async def test_get_statement_unknown_records_then_raises():
    port = FakeStatementPort(
        get_raises=StatementNotFound("no such statement", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(StatementNotFound):
        await agent.get_statement(make_get_intent(confidence=0.99))
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:StatementNotFound"


# ── cost-cap breach (token-heavy generation per-request AND per-window) ─────────


async def test_per_request_token_cap_breach_blocks_generation():
    # Document-heavy generation must be refused before any port call (ADR-047 runaway guard).
    agent, port, recorder = make_agent()
    intent = make_generate_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.generate_statement(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.generate_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_token_cap_breach_blocks():
    window = CostWindow(used_tokens=499_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.generate_statement(
        make_generate_intent(cost=RequestCost(tokens=2_000, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.generate_calls == []


async def test_window_accumulates_on_successful_read():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.get_statement(make_get_intent(cost=RequestCost(tokens=800, cost=Decimal("0.02"))))
    assert window.used_tokens == 800
    assert window.used_cost == Decimal("0.02")


# ── BLOCK / scope / process resolution ─────────────────────────────────────────


async def test_block_low_confidence_deliver():
    agent, port, recorder = make_agent()
    outcome = await agent.deliver_statement(make_deliver_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.deliver_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_read():
    agent, port, recorder = make_agent()
    outcome = await agent.get_statement(make_get_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.get_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.get_statement(make_get_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.get_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright (ADR-055 §D1).
    agent, port, recorder = make_agent(mask=make_mask(scope=("StatementPort.get_statement",)))
    outcome = await agent.list_statements(make_list_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.list_calls == []
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
    outcome = await agent.deliver_statement(
        make_deliver_intent(confidence=confidence, channel=DeliveryChannel.IN_APP),
        human_reviewed_by="dpo@banxe",
    )
    assert outcome.decision is expected


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.get_statement(make_get_intent(confidence=1.5))


# ── R-SEC: no raw PII in any lineage record ────────────────────────────────────


async def test_no_raw_pii_in_lineage_records():
    """R-SEC (R-SEC-NEW-01): lineage carries only opaque entity_id / statement_id. A PII-like
    sentinel reachable ONLY through the port's return value (the itemised statement behind the
    port) must never appear in any recorded AgentDecisionRecord field — the result rides on
    AgentOutcome.result, never on the record."""
    pii_sentinel = "IBAN-GB29-NWBK-SECRET-PII"
    # The port returns a view whose payload carries the sentinel; the entity/statement ids the
    # agent records are opaque handles only.
    port = FakeStatementPort(
        view=StatementView(
            statement_id="opaque-stmt-7",
            entity_id="opaque-ent-7",
            period=StatementPeriod.MONTH,
            opening_balance=Decimal("1.00"),
            closing_balance=Decimal("2.00"),
            line_count=1,
            currency=pii_sentinel,  # stand-in for any PII-bearing field behind the port
        )
    )
    agent, port, recorder = make_agent(port=port)
    intent = GetStatementIntent(
        intent_text="statement read request",  # caller text — contains NO raw PII
        process_ref=_ref(),
        statement_id="opaque-stmt-7",
        correlation_id="corr-opaque-1",
        confidence_score=0.99,
        request_cost=RequestCost(tokens=800, cost=Decimal("0.02")),
    )
    outcome = await agent.get_statement(intent)

    # The PII-bearing result is delivered to the caller …
    assert outcome.result.currency == pii_sentinel
    # … but NEVER recorded in lineage.
    rec = recorder.records[0]
    serialised = " ".join(
        str(v)
        for v in (
            rec.triggering_event,
            rec.intent,
            rec.reasoning_summary,
            rec.action_taken,
            rec.correlation_id,
            " ".join(rec.policies_evaluated),
            str(rec.human_reviewed_by),
        )
    )
    assert pii_sentinel not in serialised
    # Only the opaque statement_id is keyed into the lineage event.
    assert "opaque-stmt-7" in rec.triggering_event


# ── Lineage obligation (ADR-046) ───────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.get_statement(make_get_intent())
    await agent.get_statement(make_get_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "statement_client_agent"
    assert rec.intent == "Show my March statement"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 800
    assert rec.cost_amount == Decimal("0.02")
    assert rec.budget_window_ref == "statement_client_agent:default"


# ── Mask config-as-data ────────────────────────────────────────────────────────


async def test_mask_is_auto_biased_with_pii_and_egress_gate():
    mask = make_mask()
    assert mask.autonomy_level is AutonomyLevel.AUTO_BIASED
    assert mask.compliance_gate == ("PII", "DATA_EGRESS")
    assert mask.dpo_role == "DPO"
    assert mask.egress_role == "DPO"
    assert mask.in_boundary_channels == (DeliveryChannel.IN_APP,)
    assert "StatementPort.deliver_statement" in mask.scope
    assert "StatementPort.get_statement" in mask.scope


async def test_compliance_overlay_routing_values():
    # PII overlay → DPO; data-egress overlay → egress role (escalation routing is overlay-keyed).
    assert ComplianceOverlay.PII.value == "PII"
    assert ComplianceOverlay.DATA_EGRESS.value == "DATA_EGRESS"


async def test_custom_pii_escalation_role_used():
    agent, _, _ = make_agent(mask=make_mask(dpo_role="DataOfficer"))
    pii = await agent.get_statement(make_get_intent(), compliance_result=ComplianceResult.FAIL)
    assert pii.escalated_to == "DataOfficer"
