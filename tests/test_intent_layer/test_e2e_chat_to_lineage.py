"""
tests/test_intent_layer/test_e2e_chat_to_lineage.py — S8 ACCEPTANCE PROOF.

Drives a client intent string through the REAL chat→L1→L2→port→lineage chain with
an entirely in-memory stack — NO live models, NO network, NO ClickHouse:

  L1 classify (deterministic, NullLLM)
    → IntentRouter.route
      → CapabilityDispatcher runs the REAL S5.2 producers (compliance/confidence/
        cost — NOT default-PASS) and dispatches to an L2 mask
        → the mask runs its real ADR-049 §D2 gate-chain
          → emits exactly one ADR-046 AgentDecisionRecord to the in-memory sink
            → the record is retrievable by correlation_id and shape-valid.

Three required cases + one real-mask flow:
  (i)   "pay Alice £10"        → classify→route→Payments mask→PASS record
                                 (action + compliance + process_ref present);
  (ii)  a sanctions-hit intent → FAIL/ESCALATE record (producers real: a real
                                 ComplianceProducer + a sanctions check that FAILs);
  (iii) an UNRESOLVED intent   → governance event, NO dispatch (dispatcher untouched);
  (iv)  a real NotificationAgent mask flows through the SAME dispatcher (proving
        the wiring drives real masks, not only the faithful test mask).

The faithful test Payments mask mirrors the canonical §D2 chain (the same one
``services/agents/cards_agent.py`` and banxe-payment-core's ``payments_agent.py``
enforce) and uses the shared ``services/agents/_lineage`` primitives, so the
emitted record is the real schema. Live cross-repo Payments dispatch + real L3 +
the ClickHouse sink are the operator runtime step (not fabricated here).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from services.agents._lineage import (
    AgentDecisionRecord,
    AgentOutcome,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    RequestCost,
)
from services.agents._lineage import (
    ProcessRef as LineageProcessRef,
)
from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.composition import (
    CapabilityDispatcher,
    InMemoryDecisionRecorder,
)
from services.intent_layer.models import DispositionKind, IntentStatus
from services.intent_layer.ports import DispatchRequest
from services.intent_layer.router import IntentRouter
from services.producers.bundle import ProducerBundle
from services.producers.compliance_producer import ComplianceProducer
from services.producers.confidence_scorer import ConfidenceScorer
from services.producers.cost_estimator import CostEstimator
from services.producers.ports import (
    DEFAULT_COST_CAP,
    CheckOutcome,
    ComplianceCheckRequest,
)

# ── A faithful test Payments mask (real ADR-049 §D2 chain) ───────────────────


@dataclass
class _PayIntent:
    intent_text: str
    process_ref: LineageProcessRef
    amount: Decimal
    currency: str
    recipient_ref: str  # opaque handle — never a name (R-SEC)
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class _PayMask:
    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    agent_id: str = "payments_agent"
    aml_role: str = "AML"
    scope: tuple[str, ...] = ("PaymentPort.pay",)
    compliance_gate: tuple[str, ...] = ("AML",)


class _StubPaymentPort:
    """In-memory payment port — accepts the bounded transfer, returns an opaque ref."""

    def __init__(self) -> None:
        self.calls: list[tuple[Decimal, str]] = []

    async def pay(self, amount: Decimal, currency: str, recipient_ref: str) -> str:
        self.calls.append((amount, currency))
        return f"pay-receipt:{recipient_ref}"


class _PaymentsTestAgent:
    """Minimal but FAITHFUL Payments mask: enforces the fixed §D2 order
    (process_ref → scope → band → cost_cap → compliance → port) and emits exactly
    one ADR-046 record on every exit path, exactly like the real masks."""

    def __init__(self, *, port: _StubPaymentPort, recorder: DecisionRecorder, mask: _PayMask):
        self._port = port
        self._recorder = recorder
        self._mask = mask
        self._window = CostWindow(window_ref=f"{mask.agent_id}:default")

    def _band(self, confidence: float) -> ConfirmationDecision:
        if confidence > self._mask.auto_threshold:
            return ConfirmationDecision.AUTO
        if confidence >= self._mask.review_floor:
            return ConfirmationDecision.REVIEW
        return ConfirmationDecision.BLOCK

    async def pay(
        self, intent: _PayIntent, *, compliance_result: ComplianceResult = ComplianceResult.PASS
    ) -> AgentOutcome:
        policies = ["ADR-048-process-resolution", "ADR-049-scope-allow-list"]
        op = "PaymentPort.pay"
        # 1+2. process_ref + scope
        if not intent.process_ref.resolved or op not in self._mask.scope:
            return await self._emit(
                intent,
                ConfirmationDecision.BLOCK,
                "HALT_PROCESS_OR_SCOPE",
                "Unresolved process_ref or out-of-scope op.",
                policies,
                ComplianceResult.NA,
                executed=False,
                escalated_to=None,
            )
        # 3. band
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(intent.confidence_score)
        if band is not ConfirmationDecision.AUTO:
            return await self._emit(
                intent,
                band,
                "HOLD_FOR_REVIEW",
                "Below AUTO band; HITL required.",
                policies,
                compliance_result,
                executed=False,
                escalated_to=None,
            )
        # 4. cost cap
        policies.append("ADR-047-cost-cap")
        cap = self._mask.cost_cap
        if (
            intent.request_cost.tokens > cap.max_request_tokens
            or intent.request_cost.cost > cap.max_request_cost
        ):
            return await self._emit(
                intent,
                ConfirmationDecision.BLOCK,
                "HALT_COST_CAP_BREACH",
                "Cost-cap breach.",
                policies,
                ComplianceResult.NA,
                executed=False,
                escalated_to=None,
                breach=BudgetBreach.BREACH,
            )
        # 5. compliance gate (the producer-supplied verdict — never default-PASS)
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return await self._emit(
                intent,
                ConfirmationDecision.BLOCK,
                "HALT_COMPLIANCE_BLOCK",
                f"AML overlay returned {compliance_result}; blocked + escalated.",
                policies,
                compliance_result,
                executed=False,
                escalated_to=self._mask.aml_role,
            )
        # 6. commit
        await self._port.pay(intent.amount, intent.currency, intent.recipient_ref)
        self._window.add(intent.request_cost)
        return await self._emit(
            intent,
            band,
            "APPROVE_PAYMENT",
            "All §D2 gates satisfied; committing.",
            policies,
            compliance_result,
            executed=True,
            escalated_to=None,
        )

    async def _emit(
        self,
        intent,
        decision,
        action,
        reasoning,
        policies,
        compliance_result,
        *,
        executed,
        escalated_to,
        breach=BudgetBreach.NONE,
    ) -> AgentOutcome:
        from datetime import UTC, datetime
        import uuid

        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            agent_id=self._mask.agent_id,
            triggering_event=f"pay:{intent.recipient_ref}",
            intent=intent.intent_text,
            policies_evaluated=policies,
            compliance_result=compliance_result,
            reasoning_summary=reasoning,
            confidence_score=intent.confidence_score,
            action_taken=action,
            human_reviewed_by=None,
            correlation_id=intent.correlation_id,
            cost_tokens=intent.request_cost.tokens,
            cost_amount=intent.request_cost.cost,
            budget_window_ref=self._window.window_ref,
            budget_breach_flag=breach,
            escalated_to=escalated_to,
        )
        await self._recorder.record(record)
        return AgentOutcome(
            decision=decision, executed=executed, record=record, escalated_to=escalated_to
        )


# ── Dispatcher wiring (handler + sanctions stub + composition builder) ────────


def _payments_handler(request: DispatchRequest, outputs, recorder: DecisionRecorder):
    pr = request.process_refs[0]
    agent = _PaymentsTestAgent(
        port=_StubPaymentPort(),
        recorder=recorder,
        mask=_PayMask(cost_cap=DEFAULT_COST_CAP),
    )
    intent = _PayIntent(
        intent_text=request.resolved_intent.raw_text,
        process_ref=LineageProcessRef(process_id=pr.process_id, version=pr.version),
        amount=Decimal("10.00"),
        currency="GBP",
        recipient_ref=f"rcpt-{request.correlation_id}",
        correlation_id=request.correlation_id,
        confidence_score=outputs.confidence_score,
        request_cost=outputs.request_cost,
    )
    return agent.pay(intent, compliance_result=outputs.compliance_result)


class _SanctionsFail:
    """A sanctions check that FAILs when the upstream structured signal flags a hit
    (proves the produced verdict is REAL, not the agents' default-PASS)."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        if request.is_sanctions_hit:
            return CheckOutcome(
                result=ComplianceResult.FAIL,
                ref="sanctions:hit",
                reason_codes=("SANCTIONS_CONFIRMED",),
            )
        return CheckOutcome(result=ComplianceResult.PASS, ref="sanctions:clear")


def _sanctions_check_builder(request: DispatchRequest) -> ComplianceCheckRequest:
    """Represents the upstream structured sanctions signal (NOT free-text parsing)."""
    return ComplianceCheckRequest(
        action=request.resolved_intent.matched_intent or request.capability,
        correlation_id=request.correlation_id,
        subject_ref=f"subj-{request.correlation_id}",
        is_sanctions_hit=True,
    )


class _CountingDispatcher:
    """Wraps a dispatcher to assert (iii) does NOT dispatch."""

    def __init__(self, inner: CapabilityDispatcher) -> None:
        self._inner = inner
        self.calls = 0

    def dispatch(self, request: DispatchRequest):
        self.calls += 1
        return self._inner.dispatch(request)


def _benign_producers() -> ProducerBundle:
    return ProducerBundle.null()  # Null L3 ports → PASS


def _sanctions_producers() -> ProducerBundle:
    return ProducerBundle(
        compliance=ComplianceProducer(sanctions=_SanctionsFail()),
        confidence=ConfidenceScorer(),
        cost=CostEstimator(cost_cap=DEFAULT_COST_CAP),
    )


def _build_chain(catalog, *, handlers, producers, check_builder=None):
    recorder = InMemoryDecisionRecorder()
    inner = CapabilityDispatcher(
        handlers=handlers,
        producers=producers,
        recorder=recorder,
        check_request_builder=check_builder,
    )
    dispatcher = _CountingDispatcher(inner)
    classifier = IntentClassifier(catalog, enabled=True)
    router = IntentRouter(dispatcher, enabled=True)
    return classifier, router, recorder, dispatcher


# ── (i) pay → Payments mask → PASS record ────────────────────────────────────


def test_pay_intent_flows_chat_to_lineage(catalog):
    classifier, router, recorder, dispatcher = _build_chain(
        catalog, handlers={"Payments": _payments_handler}, producers=_benign_producers()
    )

    resolved = classifier.classify("pay", correlation_id="corr-pay-1")
    assert resolved.status is IntentStatus.RESOLVED
    assert resolved.capability == "Payments"

    disposition = router.route(resolved)
    assert disposition.kind is DispositionKind.DISPATCHED
    assert dispatcher.calls == 1

    record = recorder.get_by_correlation("corr-pay-1")
    assert record is not None
    # (i) record carries action + compliance + process_ref-derived lineage
    assert record.action_taken == "APPROVE_PAYMENT"
    assert record.compliance_result is ComplianceResult.PASS
    assert "ADR-048-process-resolution" in record.policies_evaluated
    assert record.agent_id == "payments_agent"
    assert record.correlation_id == "corr-pay-1"


# ── (ii) sanctions-hit → FAIL/ESCALATE record (producers REAL) ────────────────


def test_sanctions_hit_yields_fail_escalate_record(catalog):
    classifier, router, recorder, _ = _build_chain(
        catalog,
        handlers={"Payments": _payments_handler},
        producers=_sanctions_producers(),
        check_builder=_sanctions_check_builder,
    )

    resolved = classifier.classify("send money", correlation_id="corr-sanction-1")
    disposition = router.route(resolved)
    assert disposition.kind is DispositionKind.DISPATCHED

    record = recorder.get_by_correlation("corr-sanction-1")
    assert record is not None
    # The verdict was PRODUCED (real ComplianceProducer + sanctions FAIL), not default-PASS.
    assert record.compliance_result in (ComplianceResult.FAIL, ComplianceResult.ESCALATE)
    assert record.action_taken == "HALT_COMPLIANCE_BLOCK"
    assert record.escalated_to == "AML"
    assert disposition.receipt is not None
    assert disposition.receipt.metadata["executed"] == "false"


# ── (iii) UNRESOLVED → governance event, NO dispatch ─────────────────────────


def test_unresolved_intent_yields_governance_event_no_dispatch(catalog):
    classifier, router, recorder, dispatcher = _build_chain(
        catalog, handlers={"Payments": _payments_handler}, producers=_benign_producers()
    )

    resolved = classifier.classify("flibbertigibbet quux", correlation_id="corr-unresolved-1")
    assert resolved.status is IntentStatus.UNRESOLVED

    disposition = router.route(resolved)
    assert disposition.kind is DispositionKind.GOVERNANCE_EVENT
    assert dispatcher.calls == 0  # NO dispatch
    assert recorder.records == []  # NO lineage record emitted
    assert disposition.reason is not None


# ── (iv) a REAL NotificationAgent mask flows through the SAME dispatcher ──────


def test_real_notification_mask_flows_through_dispatcher(catalog):
    from api.routers.intent import _notifications_handler  # the real-mask handler

    classifier, router, recorder, dispatcher = _build_chain(
        catalog,
        handlers={"Notifications": _notifications_handler},
        producers=_benign_producers(),
    )

    resolved = classifier.classify("notifications", correlation_id="corr-notif-1")
    assert resolved.capability == "Notifications"

    disposition = router.route(resolved)
    assert disposition.kind is DispositionKind.DISPATCHED
    record = recorder.get_by_correlation("corr-notif-1")
    assert record is not None
    assert record.agent_id == "notification_agent"
    assert record.action_taken == "CHECK_CHANNEL_AVAILABLE"
    assert record.compliance_result is ComplianceResult.PASS


# ── record shape validity (matches the agent_decision_record schema fields) ───

_REQUIRED_RECORD_FIELDS = (
    "record_id",
    "timestamp",
    "agent_id",
    "triggering_event",
    "intent",
    "policies_evaluated",
    "compliance_result",
    "reasoning_summary",
    "confidence_score",
    "action_taken",
    "human_reviewed_by",
    "correlation_id",
    "cost_tokens",
    "cost_amount",
    "budget_window_ref",
    "budget_breach_flag",
)


@pytest.mark.parametrize("text,cid", [("pay", "corr-shape-1")])
def test_emitted_record_is_schema_shape_valid(catalog, text, cid):
    classifier, router, recorder, _ = _build_chain(
        catalog, handlers={"Payments": _payments_handler}, producers=_benign_producers()
    )
    router.route(classifier.classify(text, correlation_id=cid))
    record = recorder.get_by_correlation(cid)

    for field_name in _REQUIRED_RECORD_FIELDS:
        assert hasattr(record, field_name), f"record missing required field {field_name}"
    # I-05: money is Decimal, never float.
    assert isinstance(record.cost_amount, Decimal)
    assert isinstance(record.compliance_result, ComplianceResult)
    assert 0.0 <= record.confidence_score <= 1.0
