"""FPAAgent test suite — 100% branch coverage over services/agents/fpa_agent.py.

Validates: ADR-049 §D2 gate-chain branches (process-ref resolution, scope allow-list,
confidence band, cost-cap per-request and per-window, compliance gate, successful port
call, port LedgerPortError path), ADR-046 lineage invariants (one record per action on
every exit path), and R-SEC-NEW-01 (no raw GL balance in any lineage record field — the
balance rides on AgentOutcome.result only).

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
from services.agents.fpa_agent import (
    FPAAgent,
    FPAMask,
    GetBudgetActualsIntent,
    GetJournalEntryIntent,
    LedgerPortError,
)
from services.ledger.ledger_models import JournalEntry

# ---------------------------------------------------------------------------
# In-test doubles
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    """In-memory DecisionRecorder that collects records for assertion."""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeLedgerPort:
    """Duck-types the LedgerPort Protocol — no inheritance needed for Protocol types.

    Configurable balance, entry, and optional per-method raises so every gate-chain
    branch and the port-error path can be exercised independently.
    """

    def __init__(
        self,
        *,
        balance: Decimal | None = None,
        entry: JournalEntry | None = None,
        balance_raises: Exception | None = None,
        entry_raises: Exception | None = None,
    ) -> None:
        self._balance = balance if balance is not None else Decimal("1000.00")
        self._entry = entry
        self._balance_raises = balance_raises
        self._entry_raises = entry_raises
        self.balance_calls: list[str] = []
        self.entry_calls: list[str] = []

    def get_account_balance(self, account_id: str) -> Decimal:
        self.balance_calls.append(account_id)
        if self._balance_raises is not None:
            raise self._balance_raises
        return self._balance

    def get_journal_entry(self, entry_id: str) -> JournalEntry | None:
        self.entry_calls.append(entry_id)
        if self._entry_raises is not None:
            raise self._entry_raises
        return self._entry

    def get_account(self, account_id: str) -> None:
        return None

    def create_account(self, account: object) -> object:
        return account

    def post_journal_entry(self, entry: object) -> object:
        return entry


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

_DEFAULT_CAP = CostCap(
    max_request_tokens=1_000,
    max_request_cost=Decimal("1.00"),
    max_window_tokens=10_000,
    max_window_cost=Decimal("10.00"),
)


def make_mask(**overrides: object) -> FPAMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return FPAMask(**base)  # type: ignore[arg-type]


def make_agent(
    mask: FPAMask | None = None,
    port: FakeLedgerPort | None = None,
    recorder: FakeRecorder | None = None,
    window: CostWindow | None = None,
) -> tuple[FPAAgent, FakeLedgerPort, FakeRecorder]:
    p = port or FakeLedgerPort()
    r = recorder or FakeRecorder()
    m = mask or make_mask()
    return FPAAgent(ledger_port=p, recorder=r, mask=m, cost_window=window), p, r


def _ref(resolved: bool = True) -> ProcessRef:
    pid = "proc-fpa-001" if resolved else ""
    return ProcessRef(process_id=pid, version="1.0")


def _cost(tokens: int = 10, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def make_actuals_intent(
    *,
    account_id: str = "acc-001",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetBudgetActualsIntent:
    return GetBudgetActualsIntent(
        intent_text="get budget actuals for cost centre",
        process_ref=_ref(resolved),
        account_id=account_id,
        correlation_id="corr-actuals-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_entry_intent(
    *,
    entry_id: str = "jnl-001",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetJournalEntryIntent:
    return GetJournalEntryIntent(
        intent_text="get journal entry for variance drill-down",
        process_ref=_ref(resolved),
        entry_id=entry_id,
        correlation_id="corr-entry-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


# ---------------------------------------------------------------------------
# 1. AUTO happy path — get_budget_actuals
# ---------------------------------------------------------------------------


async def test_get_budget_actuals_auto_read_executes() -> None:
    """Confidence 0.95 > 0.90 → AUTO band; port called; exactly one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_budget_actuals(make_actuals_intent(account_id="acc-42"))

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert port.balance_calls == ["acc-42"]
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "GET_BUDGET_ACTUALS"
    assert rec.agent_id == "fpa_agent"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    # Balance rides on outcome.result ONLY — not on the record.
    assert outcome.result == Decimal("1000.00")
    assert outcome.record is rec


# ---------------------------------------------------------------------------
# 2. AUTO happy path — get_journal_entry
# ---------------------------------------------------------------------------


async def test_get_journal_entry_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; exactly one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_journal_entry(make_entry_intent(entry_id="jnl-99"))

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert port.entry_calls == ["jnl-99"]
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "GET_JOURNAL_ENTRY"
    # None return (entry not in store) also passes through as result.
    assert outcome.result is None


# ---------------------------------------------------------------------------
# 3. Unresolved process_ref → HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_unresolved_process_ref_blocks() -> None:
    """Empty process_id → unresolved; port NOT called; one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_budget_actuals(make_actuals_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert port.balance_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


# ---------------------------------------------------------------------------
# 4. Out-of-scope op → REJECT_OUT_OF_SCOPE
# ---------------------------------------------------------------------------


async def test_out_of_scope_op_refused() -> None:
    """Mask scope = journal-entry only; calling get_budget_actuals is off-list."""
    agent, port, recorder = make_agent(mask=make_mask(scope=("LedgerPort.get_journal_entry",)))
    outcome = await agent.get_budget_actuals(make_actuals_intent())

    assert outcome.executed is False
    assert outcome.halt_reason == "out_of_scope"
    assert port.balance_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# 5. Below-AUTO band (REVIEW) → HALT_REVIEW_DEFERRED, requires_hitl, port NOT called
# ---------------------------------------------------------------------------


async def test_below_auto_band_read_halts_review_deferred() -> None:
    """Confidence 0.80 is in REVIEW band (0.70–0.90); reads are AUTO-only (L1-Auto)."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_budget_actuals(make_actuals_intent(confidence=0.80))

    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert port.balance_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ---------------------------------------------------------------------------
# 6. Low confidence (<0.70) → BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence() -> None:
    """Confidence 0.50 < 0.70 → BLOCK; port NOT called."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_budget_actuals(make_actuals_intent(confidence=0.50))

    assert outcome.executed is False
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.balance_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# 7. Per-request token cost-cap breach → HALT_COST_CAP_BREACH, port NOT called
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_tokens_breach() -> None:
    """tokens=100 > max_request_tokens=5 → breach; port NOT called."""
    tight_cap = CostCap(
        max_request_tokens=5,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, port, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.get_budget_actuals(make_actuals_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.balance_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 8. Per-request monetary cost-cap breach → HALT_COST_CAP_BREACH
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_monetary_breach() -> None:
    """cost=0.10 > max_request_cost=0.001 → breach; port NOT called."""
    tight_cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("0.001"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, port, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.get_budget_actuals(make_actuals_intent(cost="0.10"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.balance_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 9. Per-window cost-cap breach → HALT_COST_CAP_BREACH, port NOT called
# ---------------------------------------------------------------------------


async def test_per_window_cost_cap_breach() -> None:
    """Window nearly full on tokens; next request overflows → breach."""
    # used_tokens=9990, cap max_window_tokens=10000; request 100 → 10090 > 10000.
    window = CostWindow(used_tokens=9990, used_cost=Decimal("0.00"), window_ref="fpa_agent:test")
    agent, port, recorder = make_agent(window=window)
    outcome = await agent.get_budget_actuals(make_actuals_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.balance_calls == []
    assert len(recorder.records) == 1


async def test_per_window_monetary_cost_cap_breach() -> None:
    """Window nearly full on cost; next request overflows → breach."""
    # used_cost=9.99, cap max_window_cost=10.00; request 0.02 → 10.01 > 10.00.
    window = CostWindow(used_tokens=0, used_cost=Decimal("9.99"), window_ref="fpa_agent:test")
    # Use a large token cap so only cost path triggers.
    cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=1_000_000,
        max_window_cost=Decimal("10.00"),
    )
    agent, port, recorder = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.get_budget_actuals(make_actuals_intent(tokens=1, cost="0.02"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.balance_calls == []


# ---------------------------------------------------------------------------
# 10. Compliance FAIL → BLOCK + escalate to CFO
# ---------------------------------------------------------------------------


async def test_compliance_fail_blocks_escalates_to_cfo() -> None:
    """FINANCIAL_DATA FAIL → HALT_COMPLIANCE_BLOCK; escalated_to = CFO."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_budget_actuals(
        make_actuals_intent(),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CFO"
    assert outcome.requires_hitl is True
    assert port.balance_calls == []
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.escalated_to == "CFO"
    assert rec.action_taken == "HALT_COMPLIANCE_BLOCK"


# ---------------------------------------------------------------------------
# 11. Compliance ESCALATE → BLOCK + escalate to CFO
# ---------------------------------------------------------------------------


async def test_compliance_escalate_blocks_escalates_to_cfo() -> None:
    """FINANCIAL_DATA ESCALATE also halts and escalates to CFO."""
    agent, port, recorder = make_agent()
    outcome = await agent.get_journal_entry(
        make_entry_intent(),
        compliance_result=ComplianceResult.ESCALATE,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CFO"
    assert port.entry_calls == []


# ---------------------------------------------------------------------------
# 12. Port raises LedgerPortError → lineage emitted (executed=False) then re-raised
# ---------------------------------------------------------------------------


async def test_port_error_emits_lineage_then_reraises() -> None:
    """LedgerPortError: one lineage record with HALT_PROVIDER_ERROR; error re-raised."""
    err = LedgerPortError("GL connection failed")
    port = FakeLedgerPort(balance_raises=err)
    agent, port, recorder = make_agent(port=port)

    with pytest.raises(LedgerPortError, match="GL connection failed"):
        await agent.get_budget_actuals(make_actuals_intent(account_id="acc-err"))

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert "HALT_PROVIDER_ERROR" in rec.action_taken
    assert "LedgerPortError" in rec.action_taken
    # Port was called (error raised during the call, not before it).
    assert port.balance_calls == ["acc-err"]


# ---------------------------------------------------------------------------
# 13. Confidence out of [0, 1] → ValueError, NO lineage record
# ---------------------------------------------------------------------------


async def test_invalid_confidence_above_range_raises_no_record() -> None:
    """confidence=1.1 → ValueError; _evaluate raises before any lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_budget_actuals(make_actuals_intent(confidence=1.1))
    assert len(recorder.records) == 0


async def test_invalid_confidence_below_range_raises_no_record() -> None:
    """confidence=-0.01 → ValueError; no lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_budget_actuals(make_actuals_intent(confidence=-0.01))
    assert len(recorder.records) == 0


# ---------------------------------------------------------------------------
# 14. R-SEC: no raw GL balance in any lineage record field (R-SEC-NEW-01)
# ---------------------------------------------------------------------------


async def test_no_raw_balance_in_lineage_record() -> None:
    """The GL balance sentinel MUST NOT appear in any AgentDecisionRecord field."""
    balance_sentinel = Decimal("87654321.99")
    port = FakeLedgerPort(balance=balance_sentinel)
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.get_budget_actuals(make_actuals_intent(account_id="acc-rsec"))

    # Balance rides on AgentOutcome.result — confirmed it's there.
    assert outcome.result == balance_sentinel

    rec = recorder.records[0]
    sentinel_str = str(balance_sentinel)
    # Check every string field that could carry the sentinel value.
    assert sentinel_str not in rec.triggering_event
    assert sentinel_str not in rec.intent
    assert sentinel_str not in rec.reasoning_summary
    assert sentinel_str not in rec.action_taken
    assert all(sentinel_str not in p for p in rec.policies_evaluated)
    # cost_amount is the REQUEST cost (e.g. "0.01"), not the GL balance.
    assert rec.cost_amount != balance_sentinel


# ---------------------------------------------------------------------------
# 15. Lineage-per-action (ADR-046): exactly 1 record per call on every exit path
# ---------------------------------------------------------------------------


async def test_lineage_one_record_per_call_adr046() -> None:
    """Every action call (succeed or halt) emits exactly 1 record; total increments by 1."""
    agent, _, recorder = make_agent()

    assert len(recorder.records) == 0
    await agent.get_budget_actuals(make_actuals_intent(account_id="acc-A"))
    assert len(recorder.records) == 1

    await agent.get_journal_entry(make_entry_intent(entry_id="jnl-B"))
    assert len(recorder.records) == 2

    # Halted path also emits exactly 1 record.
    await agent.get_budget_actuals(make_actuals_intent(resolved=False))
    assert len(recorder.records) == 3

    # Scope-refused also emits exactly 1 record.
    recorder2 = FakeRecorder()
    agent2, _, _ = make_agent(
        mask=make_mask(scope=("LedgerPort.get_journal_entry",)),
        recorder=recorder2,
    )
    await agent2.get_budget_actuals(make_actuals_intent())
    assert len(recorder2.records) == 1


# ---------------------------------------------------------------------------
# 16. Cost window accumulates only on successful reads (executed=True)
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_successful_reads() -> None:
    """Window.used_tokens / used_cost increment per successful port call."""
    window = CostWindow(window_ref="fpa_agent:test")
    agent, _, _ = make_agent(window=window)

    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")
    await agent.get_budget_actuals(make_actuals_intent(tokens=50, cost="0.05"))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.05")

    await agent.get_journal_entry(make_entry_intent(tokens=30, cost="0.03"))
    assert window.used_tokens == 80
    assert window.used_cost == Decimal("0.08")


async def test_window_not_accumulated_on_halt() -> None:
    """A halted call (e.g., unresolved ref) MUST NOT advance the window."""
    window = CostWindow(window_ref="fpa_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.get_budget_actuals(make_actuals_intent(resolved=False))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# 17. Port NOT called on low-band halt
# ---------------------------------------------------------------------------


async def test_port_not_called_on_band_halt() -> None:
    """REVIEW band halt must not invoke the port (L1-Auto: reads are AUTO-only)."""
    agent, port, _ = make_agent()
    await agent.get_budget_actuals(make_actuals_intent(confidence=0.75))
    assert port.balance_calls == []


# ---------------------------------------------------------------------------
# 18. In-memory e2e happy path — full flow (real mask, FakeLedgerPort, FakeRecorder)
# ---------------------------------------------------------------------------


async def test_in_memory_e2e_get_budget_actuals() -> None:
    """Full e2e: real FPAMask + FakeLedgerPort → AUTO balance read with lineage."""
    balance = Decimal("25000.00")
    port = FakeLedgerPort(balance=balance)
    recorder = FakeRecorder()
    mask = FPAMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
        agent_id="fpa_agent",
        cfo_role="CFO",
    )
    agent = FPAAgent(ledger_port=port, recorder=recorder, mask=mask)
    intent = GetBudgetActualsIntent(
        intent_text="Q1 actuals for cost centre CC-001",
        process_ref=ProcessRef(process_id="proc-e2e-fpa-001", version="1.0"),
        account_id="cc-001",
        correlation_id="e2e-corr-fpa-001",
        confidence_score=0.97,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.10")),
    )
    outcome = await agent.get_budget_actuals(intent)

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.result == balance
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.agent_id == "fpa_agent"
    assert rec.correlation_id == "e2e-corr-fpa-001"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert rec.triggering_event == "get_budget_actuals:cc-001"
    assert rec.human_reviewed_by is None  # L1-Auto: never a reviewer


async def test_in_memory_e2e_get_journal_entry() -> None:
    """Full e2e: real FPAMask + FakeLedgerPort → AUTO journal-entry read with lineage."""
    recorder = FakeRecorder()
    mask = FPAMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
    )
    agent = FPAAgent(ledger_port=FakeLedgerPort(), recorder=recorder, mask=mask)
    intent = GetJournalEntryIntent(
        intent_text="variance drill-down on entry JNL-2026-001",
        process_ref=ProcessRef(process_id="proc-e2e-fpa-002", version="1.0"),
        entry_id="JNL-2026-001",
        correlation_id="e2e-corr-fpa-002",
        confidence_score=0.93,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.05")),
    )
    outcome = await agent.get_journal_entry(intent)

    assert outcome.executed is True
    assert outcome.halt_reason is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.triggering_event == "get_journal_entry:JNL-2026-001"
    assert rec.action_taken == "GET_JOURNAL_ENTRY"
