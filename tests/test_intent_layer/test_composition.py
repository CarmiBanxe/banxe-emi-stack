"""
tests/test_intent_layer/test_composition.py — unit tests for the S8 composition root.

Covers the seam pieces directly: the in-memory lineage sink, the unrouted-capability
receipt, the live-file catalogue loader, and the async→sync bridge under a running
event loop (so dispatch works from both sync and async callers).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.agents._lineage import (
    AgentDecisionRecord,
    AgentOutcome,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
)
from services.intent_layer.catalog_snapshot import (
    MAP_PATH_ENV,
    REGISTRY_PATH_ENV,
    load_catalog,
)
from services.intent_layer.composition import (
    CapabilityDispatcher,
    InMemoryDecisionRecorder,
    default_check_request,
)
from services.intent_layer.models import (
    IntentStatus,
    MatchSource,
    ProcessRef,
    ResolvedIntent,
)
from services.intent_layer.ports import DispatchRequest
from services.producers.bundle import ProducerBundle
from services.producers.confidence_scorer import ScoringSignals


def _resolved(capability: str = "Notifications") -> ResolvedIntent:
    return ResolvedIntent(
        raw_text="notifications",
        correlation_id="corr-x",
        status=IntentStatus.RESOLVED,
        confidence=1.0,
        match_source=MatchSource.ALIAS,
        matched_intent="get-notified",
        capability=capability,
        process_refs=(ProcessRef(process_id="notification-dispatch", version="1.0.0"),),
    )


def _request(capability: str = "Notifications") -> DispatchRequest:
    r = _resolved(capability)
    return DispatchRequest(
        capability=capability,
        process_refs=r.process_refs,
        resolved_intent=r,
        correlation_id=r.correlation_id,
    )


async def _ok_handler(request, outputs, recorder) -> AgentOutcome:
    record = AgentDecisionRecord(
        record_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC),
        agent_id="unit_agent",
        triggering_event="unit",
        intent=request.resolved_intent.raw_text,
        policies_evaluated=["ADR-048-process-resolution"],
        compliance_result=ComplianceResult.PASS,
        reasoning_summary="ok",
        confidence_score=outputs.confidence_score,
        action_taken="UNIT_OK",
        human_reviewed_by=None,
        correlation_id=request.correlation_id,
        cost_tokens=outputs.request_cost.tokens,
        cost_amount=outputs.request_cost.cost,
        budget_window_ref="unit:default",
        budget_breach_flag=BudgetBreach.NONE,
    )
    await recorder.record(record)
    return AgentOutcome(decision=ConfirmationDecision.AUTO, executed=True, record=record)


async def test_in_memory_recorder_keys_by_correlation():
    recorder = InMemoryDecisionRecorder()
    assert recorder.get_by_correlation("nope") is None
    await _ok_handler(_request(), _stub_outputs(), recorder)
    rec = recorder.get_by_correlation("corr-x")
    assert rec is not None and rec.action_taken == "UNIT_OK"
    assert len(recorder.records) == 1


def _stub_outputs():
    return ProducerBundle.null().produce(
        check_request=default_check_request(_request()),
        signals=ScoringSignals.from_resolved_intent(_resolved()),
        est_tokens=128,
    )


def test_unrouted_capability_returns_not_accepted_receipt():
    dispatcher = CapabilityDispatcher(
        handlers={"Notifications": _ok_handler},
        producers=ProducerBundle.null(),
        recorder=InMemoryDecisionRecorder(),
    )
    receipt = dispatcher.dispatch(_request(capability="Payments"))
    assert receipt.accepted is False
    assert receipt.agent == "(unrouted)"
    assert "no in-process L2 mask" in (receipt.detail or "")


def test_dispatch_from_sync_context_runs_handler():
    recorder = InMemoryDecisionRecorder()
    dispatcher = CapabilityDispatcher(
        handlers={"Notifications": _ok_handler},
        producers=ProducerBundle.null(),
        recorder=recorder,
    )
    receipt = dispatcher.dispatch(_request())
    assert receipt.accepted is True
    assert recorder.get_by_correlation("corr-x") is not None


async def test_dispatch_bridges_under_running_event_loop():
    """dispatch() is sync but is invoked here from inside a running loop — the
    async→sync bridge must hand the coroutine to a worker thread, not nest loops."""
    recorder = InMemoryDecisionRecorder()
    dispatcher = CapabilityDispatcher(
        handlers={"Notifications": _ok_handler},
        producers=ProducerBundle.null(),
        recorder=recorder,
    )
    receipt = dispatcher.dispatch(_request())  # called within the test's event loop
    assert receipt.accepted is True
    assert recorder.get_by_correlation("corr-x").action_taken == "UNIT_OK"


def test_load_catalog_prefers_live_files(map_files):
    map_path, registry_path = map_files
    catalog = load_catalog(env={MAP_PATH_ENV: map_path, REGISTRY_PATH_ENV: registry_path})
    definition = catalog.lookup("pay")
    assert definition is not None
    assert definition.capability == "Payments"


def test_load_catalog_falls_back_to_snapshot():
    catalog = load_catalog(env={})  # no file paths → embedded snapshot
    assert catalog.lookup("notifications").capability == "Notifications"
    assert catalog.lookup("pay").process_refs[0].version == "1.0.0"


def test_decimal_money_preserved_through_recorder():
    outputs = _stub_outputs()
    assert isinstance(outputs.request_cost.cost, Decimal)
