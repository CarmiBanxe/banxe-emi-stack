"""
api/routers/intent.py — L1 Intent Layer HTTP entrypoint (S8).

The first HTTP surface for the ADR-049 client L1 Intent Layer. It is the chat→L1
seam: a free-form client intent enters here, L1 classifies + routes it, the
composition root populates the agent inputs from the S5.2 producers and dispatches
to the in-process L2 mask, and the emitted ADR-046 lineage record is returned and
made retrievable by ``correlation_id``.

  POST /v1/intent                          — classify + route + dispatch one intent
  GET  /v1/intent/decision/{correlation_id} — fetch the emitted lineage record

Gating (R-SEC, safe pre-activation): the whole flow sits behind
``INTENT_LAYER_ENABLED`` (default false). Disabled → a NOT_ENABLED response with NO
dispatch. The producers default to Null L3 ports (PASS) and the sink is the
in-memory recorder; the live cross-repo masks, real L3, the S1 LLM gateway and the
ClickHouse sink are the operator runtime step (do not fabricate a live run).

R-SEC: the request/record carry only the PII-minimised envelope — opaque handles,
governance metadata and a regulator-legible summary; never secrets or raw PII.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.agents._lineage import (
    AgentDecisionRecord,
    AgentOutcome,
    DecisionRecorder,
)
from services.agents._lineage import (
    ProcessRef as LineageProcessRef,
)
from services.agents.notification_agent import (
    ChannelCheckIntent,
    NotificationAgent,
    NotificationMask,
)
from services.intent_layer.canary import canary_policy_from_env
from services.intent_layer.canary_metrics import (
    CounterCanaryObserver,
    FanOutCanaryObserver,
    LoggingCanaryObserver,
)
from services.intent_layer.catalog import IntentCatalog
from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.composition import (
    CapabilityDispatcher,
    InMemoryDecisionRecorder,
)
from services.intent_layer.config import intent_layer_enabled
from services.intent_layer.models import DispositionKind
from services.intent_layer.ports import DispatchRequest
from services.intent_layer.router import IntentRouter
from services.notifications.notification_provider_port import (
    DeliveryResult,
    NotificationChannel,
    NotificationMessage,
    NotificationProviderPort,
    Recipient,
)
from services.producers.bundle import ProducerBundle
from services.producers.ports import DEFAULT_COST_CAP

router = APIRouter(tags=["Intent Layer"])


# ── Request / response schemas ───────────────────────────────────────────────


class IntentRequest(BaseModel):
    """A free-form client intent submitted from the chat surface."""

    intent_text: str = Field(..., min_length=1, description="Free-form client intent")
    correlation_id: str | None = Field(
        default=None, description="Optional caller-supplied trace id; generated when absent"
    )


class DecisionRecordModel(BaseModel):
    """Wire form of an ADR-046 ``AgentDecisionRecord`` (mirrors the agent_decision_record
    schema 1:1; ``cost_amount`` is a Decimal STRING, never a float — I-05)."""

    record_id: str
    timestamp: str
    agent_id: str
    triggering_event: str
    intent: str
    policies_evaluated: list[str]
    compliance_result: str
    reasoning_summary: str
    confidence_score: float
    action_taken: str
    human_reviewed_by: str | None
    correlation_id: str
    cost_tokens: int
    cost_amount: str
    budget_window_ref: str
    budget_breach_flag: str
    immutable_storage_ref: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class GovernanceEventModel(BaseModel):
    """Emitted when an intent resolves to no canonical process (ADR-048 D3.3) —
    HITL / process-gap backlog, never improvised, no dispatch."""

    correlation_id: str
    status: str = "UNRESOLVED"
    reason: str


class IntentResponse(BaseModel):
    """The L1 disposition: a dispatched decision record, a governance event, or a
    safe NOT_ENABLED no-op."""

    enabled: bool
    disposition: str
    decision_record: DecisionRecordModel | None = None
    governance_event: GovernanceEventModel | None = None
    detail: str | None = None


# ── Live composition root (in-process masks + Null producers + in-memory sink) ──


class _StubNotificationProvider(NotificationProviderPort):
    """In-process provider stub for the live demo: the read probe is always
    reachable, so a channel-availability intent flows end-to-end without live
    infra. A real adapter replaces it at the operator runtime step."""

    async def send(
        self, recipient: Recipient, message: NotificationMessage
    ) -> list[DeliveryResult]:
        return [DeliveryResult(channel=NotificationChannel.IN_APP, delivered=True, deduped=False)]

    async def is_channel_available(self, channel: NotificationChannel) -> bool:
        return True


def _lineage_ref(process_refs: tuple) -> LineageProcessRef:
    """Adapt the L1 ``ProcessRef`` to the agents' lineage ``ProcessRef`` (distinct
    classes by design — L1 must not depend on the agent package's internals)."""
    primary = process_refs[0]
    return LineageProcessRef(process_id=primary.process_id, version=primary.version)


async def _notifications_handler(
    request: DispatchRequest, outputs, recorder: DecisionRecorder
) -> AgentOutcome:
    """Dispatch a resolved Notifications intent to the real ``NotificationAgent``
    mask (the low-consequence channel-availability read), passing the producer
    outputs as the agent inputs (compliance/confidence/cost — not default-PASS)."""
    agent = NotificationAgent(
        provider_port=_StubNotificationProvider(),
        recorder=recorder,
        mask=NotificationMask(cost_cap=DEFAULT_COST_CAP),
    )
    intent = ChannelCheckIntent(
        intent_text=request.resolved_intent.raw_text,
        process_ref=_lineage_ref(request.process_refs),
        channel=NotificationChannel.IN_APP,
        correlation_id=request.correlation_id,
        confidence_score=outputs.confidence_score,
        request_cost=outputs.request_cost,
    )
    return await agent.check_channel(intent, compliance_result=outputs.compliance_result)


# In-process masks this deployment can dispatch. Payments/FX/Wallet are owned by
# banxe-payment-core and are reached cross-repo at the operator runtime step;
# they return an honest "unrouted" receipt here.
_LIVE_HANDLERS = {"Notifications": _notifications_handler}

# Stable singleton sink so the GET endpoint can resolve a record by the same
# correlation_id the POST returned (a per-request recorder would lose it).
_RECORDER = InMemoryDecisionRecorder()

# Stable singleton canary observer (FU-2 Phase 5): structured logs for alerting +
# in-process counters the /canary/metrics probe reads. Accumulates across requests so
# the canary's volume / withhold / error signal is monitorable for the whole process.
_CANARY_METRICS = CounterCanaryObserver()
_CANARY_OBSERVER = FanOutCanaryObserver((LoggingCanaryObserver(), _CANARY_METRICS))


@dataclass(frozen=True)
class _Composition:
    classifier: IntentClassifier
    router: IntentRouter
    recorder: InMemoryDecisionRecorder
    enabled: bool


@lru_cache(maxsize=1)
def _catalog() -> IntentCatalog:
    """Resolved intent→process catalogue. Prefers the live S3 files when their
    paths are supplied (operator wiring); otherwise an embedded snapshot keeps the
    endpoint self-contained (the canonical map lives in banxe-business-processes)."""
    from services.intent_layer.catalog_snapshot import load_catalog

    return load_catalog()


def get_composition() -> _Composition:
    """Build the request-time composition. The flag is read fresh each call (safe
    pre-activation toggling); the catalogue and the lineage sink are singletons."""
    enabled = intent_layer_enabled()
    dispatcher = CapabilityDispatcher(
        handlers=_LIVE_HANDLERS,
        producers=ProducerBundle.null(),
        recorder=_RECORDER,
    )
    # Canary gate (FU-2 Phase 5): an enabled layer auto-dispatches ONLY allowlisted,
    # non-high-risk capabilities. Policy is read fresh each call (safe toggling).
    canary = canary_policy_from_env()
    return _Composition(
        classifier=IntentClassifier(_catalog(), enabled=enabled),
        router=IntentRouter(dispatcher, enabled=enabled, canary=canary, observer=_CANARY_OBSERVER),
        recorder=_RECORDER,
        enabled=enabled,
    )


# ── Serialisation ────────────────────────────────────────────────────────────


def _to_record_model(record: AgentDecisionRecord) -> DecisionRecordModel:
    return DecisionRecordModel(
        record_id=record.record_id,
        timestamp=record.timestamp.isoformat(),
        agent_id=record.agent_id,
        triggering_event=record.triggering_event,
        intent=record.intent,
        policies_evaluated=list(record.policies_evaluated),
        compliance_result=record.compliance_result.value,
        reasoning_summary=record.reasoning_summary,
        confidence_score=record.confidence_score,
        action_taken=record.action_taken,
        human_reviewed_by=record.human_reviewed_by,
        correlation_id=record.correlation_id,
        cost_tokens=record.cost_tokens,
        cost_amount=str(record.cost_amount),  # Decimal → string (I-05)
        budget_window_ref=record.budget_window_ref,
        budget_breach_flag=record.budget_breach_flag.value,
        immutable_storage_ref=record.immutable_storage_ref,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/intent", response_model=IntentResponse)
def submit_intent(body: IntentRequest) -> IntentResponse:
    """Classify + route + dispatch one client intent (chat→L1→L2→port→lineage).

    Synchronous handler by design: FastAPI runs it in the threadpool, so the
    composition's async L2 masks are driven via ``asyncio.run`` with no nested
    event loop. Off → NOT_ENABLED (no dispatch). UNRESOLVED → governance event.
    """
    comp = get_composition()
    resolved = comp.classifier.classify(body.intent_text, correlation_id=body.correlation_id)
    disposition = comp.router.route(resolved)

    if disposition.kind is DispositionKind.NOT_ENABLED:
        return IntentResponse(enabled=False, disposition="NOT_ENABLED", detail=disposition.reason)

    if disposition.kind is DispositionKind.GOVERNANCE_EVENT:
        return IntentResponse(
            enabled=True,
            disposition="GOVERNANCE_EVENT",
            governance_event=GovernanceEventModel(
                correlation_id=disposition.correlation_id,
                reason=disposition.reason or "intent resolved to no canonical process",
            ),
        )

    receipt = disposition.receipt
    if receipt is None or not getattr(receipt, "accepted", False):
        detail = getattr(receipt, "detail", None) if receipt else None
        return IntentResponse(enabled=True, disposition="DISPATCHED", detail=detail)

    record = comp.recorder.get_by_correlation(disposition.correlation_id)
    return IntentResponse(
        enabled=True,
        disposition="DISPATCHED",
        decision_record=_to_record_model(record) if record else None,
        detail=getattr(receipt, "detail", None),
    )


@router.get("/intent/decision/{correlation_id}", response_model=DecisionRecordModel)
def get_decision(correlation_id: str) -> DecisionRecordModel:
    """Fetch the lineage record emitted for a correlation id (backs the UI
    decisions.getByCorrelation client). 404 when none was recorded."""
    record = _RECORDER.get_by_correlation(correlation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no decision record for correlation_id")
    return _to_record_model(record)


@router.get("/intent/canary/metrics")
def get_canary_metrics() -> dict[str, int]:
    """Read-only canary monitoring counters (FU-2 Phase 5): canary intents seen,
    dispatched, withheld (not-canary / high-risk) and error totals. Backs canary
    observation in staging; no PII, just decision counts."""
    return _CANARY_METRICS.snapshot()
