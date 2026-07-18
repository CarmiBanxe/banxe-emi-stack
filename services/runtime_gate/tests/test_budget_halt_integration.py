"""S-A2 C-3 exit-criterion: integration test of the full budget-halt chain —
tiny cap → BudgetExceededError → durable lineage record (BREACH) → HITL queue.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents._lineage import BudgetBreach, ComplianceResult
from services.agents.recorders import InMemoryDecisionRecorder
from services.runtime_gate.budget import BudgetManager, load_budget
from services.runtime_gate.budget_halt import (
    HALT_ACTION,
    BudgetExceededError,
    BudgetHaltGate,
    InMemoryHitlQueue,
)
from services.runtime_gate.errors import BudgetConfigError, OverBudget
from services.runtime_gate.metrics import InMemoryMetrics


def _gate(budget_file, metrics=None, paths=None):
    recorder = InMemoryDecisionRecorder()
    hitl = InMemoryHitlQueue()
    manager = BudgetManager(load_budget(budget_file), metrics=metrics)
    return BudgetHaltGate(manager, recorder, hitl, escalation_paths=paths), recorder, hitl


async def test_within_budget_charges_without_lineage_or_hitl(budget_file):
    gate, recorder, hitl = _gate(budget_file)
    await gate.charge(
        "audit_trail",
        600,
        Decimal("1.00"),
        intent="daily audit export",
        triggering_event="cron:audit",
        correlation_id="c-1",
    )
    assert recorder.query(agent_id="audit_trail") == []
    assert hitl.items == []


async def test_breach_halts_records_breach_and_enqueues_hitl(budget_file):
    metrics = InMemoryMetrics()
    gate, recorder, hitl = _gate(budget_file, metrics=metrics, paths={"audit_trail": "cfo_queue"})
    await gate.charge(
        "audit_trail",
        600,
        Decimal("1.00"),
        intent="daily audit export",
        triggering_event="cron:audit",
        correlation_id="c-2",
    )
    with pytest.raises(BudgetExceededError):
        await gate.charge(
            "audit_trail",
            600,
            Decimal("0.10"),
            intent="daily audit export",
            triggering_event="cron:audit",
            correlation_id="c-2",
        )
    (record,) = recorder.query(agent_id="audit_trail")
    assert record.budget_breach_flag is BudgetBreach.BREACH
    assert record.compliance_result is ComplianceResult.ESCALATE
    assert record.action_taken == HALT_ACTION
    assert record.escalated_to == "cfo_queue"
    assert record.correlation_id == "c-2"
    assert record.cost_amount == Decimal("0.10")
    (item,) = hitl.items
    assert item.queue == "cfo_queue"
    assert item.record_id == record.record_id
    assert metrics.value("budget_exceeded", "audit_trail") == 1


async def test_budget_exceeded_error_is_overbudget_subclass(budget_file):
    gate, _, _ = _gate(budget_file)
    with pytest.raises(OverBudget):  # backward compat: existing handlers keep working
        await gate.charge(
            "audit_trail",
            2000,
            Decimal("0.10"),
            intent="i",
            triggering_event="e",
            correlation_id="c-3",
        )


async def test_missing_policy_stays_fail_closed_without_lineage(budget_file):
    gate, recorder, hitl = _gate(budget_file)
    with pytest.raises(BudgetConfigError):
        await gate.charge(
            "unknown_agent",
            1,
            Decimal("0.01"),
            intent="i",
            triggering_event="e",
            correlation_id="c-4",
        )
    assert recorder.query(agent_id="unknown_agent") == []
    assert hitl.items == []


async def test_default_escalation_queue_when_no_path_configured(budget_file):
    gate, recorder, hitl = _gate(budget_file)
    with pytest.raises(BudgetExceededError):
        await gate.charge(
            "audit_trail",
            2000,
            Decimal("0.10"),
            intent="i",
            triggering_event="e",
            correlation_id="c-5",
        )
    (record,) = recorder.query(agent_id="audit_trail")
    assert record.escalated_to == "human_review_queue"
    assert hitl.items[0].queue == "human_review_queue"
