"""ChurnPredictionAgent test suite — 100% coverage over
services/agents/churn_prediction_agent.py.

Validates: ADR-049 §D2 gate-chain branches (process-ref resolution, scope allow-list,
confidence band, cost-cap per-request and per-window, PII compliance gate, successful port
call, port ChurnSignalPortError path), ADR-046 lineage invariants (one record per action on
every exit path), R-SEC-NEW-01 (no raw risk score / signal weight / PII in any lineage
record — result rides on AgentOutcome.result only), and the DETECTION/REPORTING INVARIANT
(mask scope has no retention / trigger / write op; the agent never mutates customer state;
all success_actions use DETECT_ or REPORT_ prefix).

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected
without @pytest.mark.asyncio.
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
from services.agents.churn_prediction_agent import (
    AtRiskScanIntent,
    ChurnPredictionAgent,
    ChurnPredictionMask,
    ChurnSignalsIntent,
)
from services.churn.churn_signal_port import (
    AtRiskCustomer,
    ChurnSignal,
    ChurnSignalCode,
    ChurnSignalPortError,
    ChurnSignalSet,
    InMemoryChurnSignalPort,
    RiskBand,
)

# ---------------------------------------------------------------------------
# In-test doubles
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    """In-memory DecisionRecorder that collects records for assertion."""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

_DEFAULT_CAP = CostCap(
    max_request_tokens=1_000,
    max_request_cost=Decimal("1.00"),
    max_window_tokens=10_000,
    max_window_cost=Decimal("10.00"),
)


def make_mask(**overrides: object) -> ChurnPredictionMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return ChurnPredictionMask(**base)  # type: ignore[arg-type]


def make_agent(
    mask: ChurnPredictionMask | None = None,
    port: InMemoryChurnSignalPort | None = None,
    recorder: FakeRecorder | None = None,
    window: CostWindow | None = None,
) -> tuple[ChurnPredictionAgent, InMemoryChurnSignalPort, FakeRecorder]:
    p = port or InMemoryChurnSignalPort()
    r = recorder or FakeRecorder()
    m = mask or make_mask()
    return ChurnPredictionAgent(churn_signal_port=p, recorder=r, mask=m, cost_window=window), p, r


def _ref(resolved: bool = True) -> ProcessRef:
    pid = "proc-churn-001" if resolved else ""
    return ProcessRef(process_id=pid, version="1.0")


def _cost(tokens: int = 10, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def make_scan_intent(
    *,
    cohort: str = "retail-eu",
    threshold: str = "0.50",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> AtRiskScanIntent:
    return AtRiskScanIntent(
        cohort=cohort,
        threshold=Decimal(threshold),
        intent_text="report at-risk customers for retail-eu cohort",
        process_ref=_ref(resolved),
        correlation_id="corr-scan-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_signals_intent(
    *,
    customer_id: str = "cust-1001",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> ChurnSignalsIntent:
    return ChurnSignalsIntent(
        customer_id=customer_id,
        intent_text="detect churn signals for a customer",
        process_ref=_ref(resolved),
        correlation_id="corr-signals-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


# ---------------------------------------------------------------------------
# 1-2. AUTO happy paths
# ---------------------------------------------------------------------------


async def test_report_at_risk_auto_read_executes() -> None:
    """Confidence 0.95 > 0.90 → AUTO band; port called; exactly one lineage record."""
    agent, _, recorder = make_agent()
    outcome = await agent.report_at_risk_customers(make_scan_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert isinstance(outcome.result, list)
    assert all(isinstance(c, AtRiskCustomer) for c in outcome.result)
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "REPORT_AT_RISK"
    assert rec.agent_id == "churn_prediction_agent"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert rec.triggering_event == "get_at_risk_customers:retail-eu"
    assert outcome.record is rec


async def test_get_churn_signals_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is ChurnSignalSet."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_churn_signals(make_signals_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, ChurnSignalSet)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "DETECT_CHURN_SIGNALS"
    assert recorder.records[0].triggering_event == "get_churn_signals:cust-1001"


# ---------------------------------------------------------------------------
# 3. Unresolved process_ref → HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_unresolved_process_ref_blocks() -> None:
    agent, _, recorder = make_agent()
    outcome = await agent.report_at_risk_customers(make_scan_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


# ---------------------------------------------------------------------------
# 4. Out-of-scope op → REJECT_OUT_OF_SCOPE (retention-trigger op refused)
# ---------------------------------------------------------------------------


async def test_out_of_scope_retention_trigger_refused() -> None:
    """Scope restricted to a retention-trigger (mutate) op; the read op is off-list → REJECT.

    INVARIANT: ChurnSignalPort.trigger_retention is never in the default allow-list. When a
    scope containing only a mutate op is configured, the read op is REJECT_OUT_OF_SCOPE —
    demonstrating a retention/write op cannot be reached via the normal agent flow (the port
    also has no such method).
    """
    scoped_mask = make_mask(scope=("ChurnSignalPort.trigger_retention",))
    agent, port, recorder = make_agent(mask=scoped_mask)
    outcome = await agent.report_at_risk_customers(make_scan_intent())

    assert outcome.executed is False
    assert outcome.halt_reason == "out_of_scope"
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# 5. Below-AUTO band (REVIEW) → HALT_REVIEW_DEFERRED, port NOT called
# ---------------------------------------------------------------------------


async def test_below_auto_band_read_halts_review_deferred() -> None:
    """Confidence 0.80 is in REVIEW band (0.70–0.90); reads are AUTO-only (L1-Auto)."""
    agent, _, recorder = make_agent()
    outcome = await agent.report_at_risk_customers(make_scan_intent(confidence=0.80))

    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_band_boundary_exactly_auto_threshold_is_review() -> None:
    """confidence=0.90 is NOT > 0.90 → REVIEW band → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.report_at_risk_customers(make_scan_intent(confidence=0.90))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


async def test_band_boundary_exactly_review_floor_is_review() -> None:
    """confidence=0.70 is >= 0.70 → REVIEW band → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.get_churn_signals(make_signals_intent(confidence=0.70))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


# ---------------------------------------------------------------------------
# 6. Low confidence (<0.70) → BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence() -> None:
    agent, _, recorder = make_agent()
    outcome = await agent.report_at_risk_customers(make_scan_intent(confidence=0.50))

    assert outcome.executed is False
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# 7. Cost-cap breaches — per-request (tokens + monetary) and per-window
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_tokens_breach() -> None:
    tight_cap = CostCap(
        max_request_tokens=5,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.report_at_risk_customers(make_scan_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


async def test_per_request_cost_cap_monetary_breach() -> None:
    tight_cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("0.001"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.report_at_risk_customers(make_scan_intent(cost="0.10"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


async def test_per_window_token_cost_cap_breach() -> None:
    window = CostWindow(
        used_tokens=9990, used_cost=Decimal("0.00"), window_ref="churn_prediction_agent:test"
    )
    agent, _, recorder = make_agent(window=window)
    outcome = await agent.report_at_risk_customers(make_scan_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert len(recorder.records) == 1


async def test_per_window_monetary_cost_cap_breach() -> None:
    window = CostWindow(
        used_tokens=0, used_cost=Decimal("9.99"), window_ref="churn_prediction_agent:test"
    )
    cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=1_000_000,
        max_window_cost=Decimal("10.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.report_at_risk_customers(make_scan_intent(tokens=1, cost="0.02"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# 8. PII compliance gate → HALT_COMPLIANCE_BLOCK, escalated to DPO
# ---------------------------------------------------------------------------


async def test_compliance_fail_blocks_escalates_to_dpo() -> None:
    agent, _, recorder = make_agent()
    outcome = await agent.report_at_risk_customers(
        make_scan_intent(), compliance_result=ComplianceResult.FAIL
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "DPO"
    assert outcome.requires_hitl is True
    rec = recorder.records[0]
    assert rec.escalated_to == "DPO"
    assert rec.action_taken == "HALT_COMPLIANCE_BLOCK"
    assert rec.compliance_result is ComplianceResult.FAIL


async def test_compliance_escalate_blocks_escalates_to_dpo() -> None:
    agent, _, recorder = make_agent()
    outcome = await agent.get_churn_signals(
        make_signals_intent(), compliance_result=ComplianceResult.ESCALATE
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "DPO"
    assert len(recorder.records) == 1


async def test_custom_dpo_role_used() -> None:
    agent, _, _ = make_agent(mask=make_mask(dpo_role="DataProtectionOfficer"))
    outcome = await agent.report_at_risk_customers(
        make_scan_intent(), compliance_result=ComplianceResult.FAIL
    )
    assert outcome.escalated_to == "DataProtectionOfficer"


# ---------------------------------------------------------------------------
# 9. Port raises ChurnSignalPortError → lineage emitted (executed=False), re-raised
# ---------------------------------------------------------------------------


async def test_port_error_emits_lineage_then_reraises_on_scan() -> None:
    port = InMemoryChurnSignalPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(ChurnSignalPortError):
        await agent.report_at_risk_customers(make_scan_intent())

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert "HALT_PROVIDER_ERROR" in rec.action_taken
    assert "ChurnSignalPortError" in rec.action_taken


async def test_port_error_emits_lineage_then_reraises_on_signals() -> None:
    port = InMemoryChurnSignalPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(ChurnSignalPortError):
        await agent.get_churn_signals(make_signals_intent())

    assert len(recorder.records) == 1
    assert "HALT_PROVIDER_ERROR" in recorder.records[0].action_taken


async def test_port_customer_not_found_reraised_as_provider_error() -> None:
    """A CustomerNotFound (ChurnSignalPortError subclass) is recorded then re-raised."""
    port = InMemoryChurnSignalPort(signals={})
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(ChurnSignalPortError):
        await agent.get_churn_signals(make_signals_intent(customer_id="ghost"))

    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:CustomerNotFound"


# ---------------------------------------------------------------------------
# 10. Invalid confidence → ValueError, NO lineage record
# ---------------------------------------------------------------------------


async def test_invalid_confidence_above_range_raises_no_record() -> None:
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.report_at_risk_customers(make_scan_intent(confidence=1.1))
    assert len(recorder.records) == 0


async def test_invalid_confidence_below_range_raises_no_record() -> None:
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_churn_signals(make_signals_intent(confidence=-0.01))
    assert len(recorder.records) == 0


# ---------------------------------------------------------------------------
# 11. R-SEC: no raw risk score / signal weight in any lineage record field
# ---------------------------------------------------------------------------


async def test_no_raw_risk_score_in_lineage_record() -> None:
    """A risk-score sentinel reachable ONLY through the port result MUST NOT appear in any
    AgentDecisionRecord field — the ChurnSignalSet rides on AgentOutcome.result only."""
    sentinel = Decimal("0.87654321")
    signal_set = ChurnSignalSet(
        customer_id="cust-opaque-7",
        cohort="retail-eu",
        risk_score=sentinel,
        band=RiskBand.HIGH,
        signals=(ChurnSignal(code=ChurnSignalCode.DORMANCY, weight=Decimal("0.99119911")),),
    )
    port = InMemoryChurnSignalPort(signals={"cust-opaque-7": signal_set})
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.get_churn_signals(make_signals_intent(customer_id="cust-opaque-7"))

    # Result delivered to the caller …
    assert isinstance(outcome.result, ChurnSignalSet)
    assert outcome.result.risk_score == sentinel  # type: ignore[union-attr]

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
        )
    )
    assert str(sentinel) not in serialised
    assert "0.99119911" not in serialised
    assert rec.cost_amount != sentinel
    # Only the opaque customer_id is keyed into the lineage event.
    assert "cust-opaque-7" in rec.triggering_event


# ---------------------------------------------------------------------------
# 12. ADR-046 lineage-per-action + window accumulation
# ---------------------------------------------------------------------------


async def test_lineage_one_record_per_call_adr046() -> None:
    agent, _, recorder = make_agent()

    assert len(recorder.records) == 0
    await agent.report_at_risk_customers(make_scan_intent())
    assert len(recorder.records) == 1
    await agent.get_churn_signals(make_signals_intent())
    assert len(recorder.records) == 2
    # A halted path also emits exactly 1 record.
    await agent.report_at_risk_customers(make_scan_intent(resolved=False))
    assert len(recorder.records) == 3


async def test_window_accumulates_on_successful_reads() -> None:
    window = CostWindow(window_ref="churn_prediction_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.report_at_risk_customers(make_scan_intent(tokens=50, cost="0.05"))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.05")

    await agent.get_churn_signals(make_signals_intent(tokens=30, cost="0.03"))
    assert window.used_tokens == 80
    assert window.used_cost == Decimal("0.08")


async def test_window_not_accumulated_on_halt() -> None:
    window = CostWindow(window_ref="churn_prediction_agent:test")
    agent, _, _ = make_agent(window=window)
    await agent.report_at_risk_customers(make_scan_intent(resolved=False))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


async def test_default_window_ref_uses_agent_id() -> None:
    agent, _, _ = make_agent()
    assert agent._window.window_ref == "churn_prediction_agent:default"


# ---------------------------------------------------------------------------
# 13. INVARIANT: read-only — no state mutation; scope + success_actions verified
# ---------------------------------------------------------------------------


async def test_invariant_scope_is_detect_report_only() -> None:
    """Default mask scope MUST contain ONLY the 2 read ops — no retention/trigger/write op."""
    mask = make_mask()
    scope_lower = " ".join(mask.scope).lower()
    for forbidden in ("retention", "trigger", "write", "update", "suspend", "close"):
        assert forbidden not in scope_lower
    assert set(mask.scope) == {
        "ChurnSignalPort.get_at_risk_customers",
        "ChurnSignalPort.get_churn_signals",
    }


async def test_invariant_no_customer_state_mutation() -> None:
    """A full read flow MUST NOT mutate the port's customer-state data (read-only invariant).

    The agent has no mutate capability; this asserts the port snapshot is byte-identical
    before and after a successful read, and that success_actions are DETECT/REPORT verbs only.
    """
    port = InMemoryChurnSignalPort()
    before = await port.get_churn_signals("cust-1001")
    agent, _, recorder = make_agent(port=port)

    await agent.report_at_risk_customers(make_scan_intent(threshold="0"))
    await agent.get_churn_signals(make_signals_intent(customer_id="cust-1001"))

    after = await port.get_churn_signals("cust-1001")
    assert after == before  # frozen snapshot unchanged — no mutation

    actions = " ".join(r.action_taken for r in recorder.records)
    assert all(
        a.startswith(("DETECT_", "REPORT_")) for a in [r.action_taken for r in recorder.records]
    )
    for token in ("RETENTION", "TRIGGER", "WRITE", "UPDATE", "SUSPEND"):
        assert token not in actions


# ---------------------------------------------------------------------------
# 14. In-memory e2e full flow (real mask, InMemoryChurnSignalPort, FakeRecorder)
# ---------------------------------------------------------------------------


async def test_in_memory_e2e_report_at_risk() -> None:
    recorder = FakeRecorder()
    mask = ChurnPredictionMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
        agent_id="churn_prediction_agent",
        dpo_role="DPO",
    )
    port = InMemoryChurnSignalPort()
    agent = ChurnPredictionAgent(churn_signal_port=port, recorder=recorder, mask=mask)
    intent = AtRiskScanIntent(
        cohort="retail-eu",
        threshold=Decimal("0.40"),
        intent_text="CustomerOps daily at-risk scan Q2-2026",
        process_ref=ProcessRef(process_id="proc-e2e-churn-001", version="1.0"),
        correlation_id="e2e-corr-churn-001",
        confidence_score=0.97,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.10")),
    )
    outcome = await agent.report_at_risk_customers(intent)

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, list)
    assert outcome.result[0].risk_score == Decimal("0.82")  # highest-risk first (cust-1001)
    assert outcome.halt_reason is None
    rec = recorder.records[0]
    assert rec.correlation_id == "e2e-corr-churn-001"
    assert rec.triggering_event == "get_at_risk_customers:retail-eu"
    assert rec.human_reviewed_by is None  # L1-Auto: never a reviewer
