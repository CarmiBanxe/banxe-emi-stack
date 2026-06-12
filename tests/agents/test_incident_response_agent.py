"""Tests for the ORG §2.7.4 / FCA SYSC 8.1 incident-response mask agent
(services/agents/incident_response_agent.py).

Covers every mask path in the §D2 gate-chain order: AUTO reads (list/inspect),
non-critical triage AUTO + REVIEW (hold then proceed), the CRITICAL-escalation
invariant (critical @ confidence 1.0 with no reviewer → HALT, forced step-up to
CTO+CEO, ≤2h SLA, disposition never committed / incident never closed) and the
critical-with-reviewer proceed path, HALT_UNRESOLVED_PROCESS, REJECT_OUT_OF_SCOPE
(auto-close refused), HALT_REVIEW_DEFERRED, BLOCK_LOW_CONFIDENCE (critical +
non-critical), HALT_COST_CAP_BREACH (per-request + per-window), HALT_COMPLIANCE_BLOCK,
HALT_PROVIDER_ERROR (emit + reraise), invalid confidence → ValueError, R-SEC, and the
one-lineage-record-per-action obligation (ADR-046). The port and recorder are fakes —
the agent is exercised as pure governance logic with no live infra.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.incident_response_agent import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    IncidentResponseAgent,
    IncidentResponseMask,
    InspectIncidentIntent,
    ListIncidentsIntent,
    ProcessRef,
    RequestCost,
    TriageIncidentIntent,
)
from services.incident_response.incident_signal_port import (
    IncidentSeverity,
    IncidentSource,
    IncidentStatus,
    InMemoryIncidentSignalPort,
    SignalSourceUnavailable,
)

# ── Fakes / builders ───────────────────────────────────────────────────────────


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


def make_mask(**overrides) -> IncidentResponseMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return IncidentResponseMask(**base)


def make_agent(
    *,
    mask: IncidentResponseMask | None = None,
    port: InMemoryIncidentSignalPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[IncidentResponseAgent, InMemoryIncidentSignalPort, FakeRecorder]:
    port = port or InMemoryIncidentSignalPort()
    recorder = recorder or FakeRecorder()
    agent = IncidentResponseAgent(
        signal_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-INCIDENT-TRIAGE", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_list_intent(
    *, confidence: float = 0.99, severity: IncidentSeverity | None = None
) -> ListIncidentsIntent:
    return ListIncidentsIntent(
        intent_text="List open security incidents",
        process_ref=_ref(),
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.01")),
        severity=severity,
    )


def make_inspect_intent(*, confidence: float = 0.99) -> InspectIncidentIntent:
    return InspectIncidentIntent(
        intent_text="Inspect incident INC-1",
        process_ref=_ref(),
        incident_id="INC-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.01")),
    )


def make_triage_intent(
    *,
    severity: IncidentSeverity = IncidentSeverity.MEDIUM,
    confidence: float = 0.95,
    cost: RequestCost | None = None,
    resolved: bool = True,
) -> TriageIncidentIntent:
    return TriageIncidentIntent(
        intent_text="Triage incident INC-1",
        process_ref=_ref(resolved),
        incident_id="INC-1",
        severity=severity,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=400, cost=Decimal("0.04")),
    )


# ── AUTO reads (list / inspect) ────────────────────────────────────────────────


async def test_list_incidents_auto_executes():
    agent, port, recorder = make_agent()
    port.add_incident("INC-1", signal_score=10)
    outcome = await agent.list_incidents(make_list_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert port.get_incidents_calls == [None]
    assert recorder.records[0].action_taken == "LIST_INCIDENTS"
    assert len(recorder.records) == 1


async def test_list_incidents_with_severity_filter_labels_event():
    agent, port, recorder = make_agent()
    port.add_incident("INC-CRIT", signal_score=90)
    outcome = await agent.list_incidents(
        make_list_intent(confidence=0.99, severity=IncidentSeverity.CRITICAL)
    )
    assert outcome.executed is True
    assert recorder.records[0].triggering_event == "list_incidents:CRITICAL"


async def test_inspect_incident_auto_executes():
    agent, port, recorder = make_agent()
    port.add_incident("INC-1", signal_score=88, source=IncidentSource.ANOMALY_DETECTOR)
    outcome = await agent.inspect_incident(make_inspect_intent())

    assert outcome.executed is True
    assert outcome.result is not None
    assert port.get_incident_calls == ["INC-1"]
    assert recorder.records[0].action_taken == "INSPECT_INCIDENT"


async def test_read_below_auto_band_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.list_incidents(make_list_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.get_incidents_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── Non-critical triage (AUTO / REVIEW hold + proceed) ─────────────────────────


async def test_noncritical_triage_auto_executes():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.MEDIUM, confidence=0.95)
    )
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.sla_hours is None  # non-critical carries no SLA
    assert recorder.records[0].action_taken == "TRIAGE_INCIDENT"


async def test_noncritical_triage_review_band_holds_for_hitl():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.HIGH, confidence=0.80)
    )
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"


async def test_noncritical_triage_review_with_reviewer_proceeds():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.HIGH, confidence=0.80),
        human_reviewed_by="soc-lead@banxe",
    )
    assert outcome.executed is True
    assert recorder.records[0].human_reviewed_by == "soc-lead@banxe"
    assert recorder.records[0].action_taken == "TRIAGE_INCIDENT"


# ── CRITICAL escalation invariant (FCA SYSC 8.1) ───────────────────────────────


async def test_critical_at_full_confidence_no_reviewer_halts_and_escalates():
    """The marquee invariant: a CRITICAL incident at confidence 1.0 with NO reviewer
    can NEVER be auto-closed — it forces a CTO+CEO step-up with a ≤2h SLA and never
    commits a disposition (the incident is left untouched / never closed)."""
    agent, port, recorder = make_agent()
    port.add_incident("INC-1", signal_score=99, status=IncidentStatus.OPEN)

    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.CRITICAL, confidence=1.0)
    )

    assert outcome.executed is False  # disposition NEVER committed
    assert outcome.requires_step_up is True
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "CTO+CEO"
    assert outcome.sla_hours == 2
    assert outcome.halt_reason == "critical_escalation_required"
    assert recorder.records[0].action_taken == "HALT_CRITICAL_ESCALATION_REQUIRED"
    assert recorder.records[0].escalated_to == "CTO+CEO"
    assert "SYSC8.1-CRITICAL-CTO-CEO-step-up" in recorder.records[0].policies_evaluated
    # close never called: the incident is left exactly as it was (no domain mutation).
    assert (await port.get_incident("INC-1")).status is IncidentStatus.OPEN


async def test_critical_with_reviewer_proceeds_under_signoff():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.CRITICAL, confidence=0.99),
        human_reviewed_by="cto-ceo@banxe",
    )
    assert outcome.executed is True
    assert outcome.sla_hours == 2  # SYSC 8.1 SLA surfaced even on the signed-off path
    assert recorder.records[0].human_reviewed_by == "cto-ceo@banxe"
    assert recorder.records[0].action_taken == "TRIAGE_INCIDENT"


async def test_critical_low_confidence_blocks_and_escalates_with_sla():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.CRITICAL, confidence=0.50)
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "CTO+CEO"
    assert outcome.sla_hours == 2
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_critical_step_up_cannot_be_disabled_by_mask_config():
    # The CRITICAL step-up is a regulatory floor — even a permissive mask cannot auto-close.
    agent, _, recorder = make_agent(mask=make_mask(auto_threshold=0.0, review_floor=0.0))
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.CRITICAL, confidence=1.0)
    )
    assert outcome.executed is False
    assert recorder.records[0].action_taken == "HALT_CRITICAL_ESCALATION_REQUIRED"


# ── BLOCK / scope / process resolution ─────────────────────────────────────────


async def test_noncritical_low_confidence_blocks_without_escalation():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.MEDIUM, confidence=0.40)
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.escalated_to is None
    assert outcome.sla_hours is None
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(make_triage_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused_auto_close():
    # An op not on the mask allow-list is refused outright — a close/suppress op is
    # never on the list, so auto-close is structurally refused.
    agent, _, recorder = make_agent(mask=make_mask(scope=("IncidentSignalPort.get_incidents",)))
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.MEDIUM, confidence=0.95)
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


# ── Cost-cap breach ────────────────────────────────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, _, recorder = make_agent()
    intent = make_triage_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.triage_incident(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, _, _ = make_agent(cost_window=window)
    outcome = await agent.triage_incident(
        make_triage_intent(cost=RequestCost(tokens=200, cost=Decimal("0.01")))
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"


async def test_window_accumulates_on_successful_action():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.triage_incident(
        make_triage_intent(confidence=0.95, cost=RequestCost(tokens=300, cost=Decimal("0.02")))
    )
    assert window.used_tokens == 300
    assert window.used_cost == Decimal("0.02")


# ── Compliance gate → CTO+CEO escalation ───────────────────────────────────────


async def test_compliance_fail_blocks_and_escalates():
    agent, _, recorder = make_agent()
    outcome = await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.MEDIUM),
        compliance_result=ComplianceResult.FAIL,
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.escalated_to == "CTO+CEO"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


# ── Provider error (emit + reraise) ────────────────────────────────────────────


async def test_provider_error_records_then_raises():
    port = InMemoryIncidentSignalPort()
    port.add_incident("INC-1", signal_score=10)
    port.set_unavailable(SignalSourceUnavailable("siem down", correlation_id="corr-1"))
    agent, port, recorder = make_agent(port=port)

    with pytest.raises(SignalSourceUnavailable):
        await agent.inspect_incident(make_inspect_intent())

    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:SignalSourceUnavailable"


# ── R-SEC + lineage obligation (ADR-046) ───────────────────────────────────────


async def test_rsec_lineage_carries_opaque_metadata_only():
    agent, _, recorder = make_agent()
    await agent.triage_incident(
        make_triage_intent(severity=IncidentSeverity.CRITICAL, confidence=1.0)
    )
    rec = recorder.records[0]
    # Only incident_id/severity ride on the record — never raw security data or PII.
    assert "INC-1" in rec.triggering_event
    assert "CRITICAL" in rec.triggering_event
    assert rec.agent_id == "incident_response_agent"


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.triage_incident(make_triage_intent(confidence=0.95))
    await agent.triage_incident(make_triage_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "incident_response_agent"
    assert rec.intent == "Triage incident INC-1"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 400
    assert rec.budget_window_ref == "incident_response_agent:default"


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.triage_incident(make_triage_intent(confidence=1.5))
