"""ContractAgent §D2 mask — 100% branch coverage.

Gate chain (ADR-049 §D2): process_ref → scope → band [+Legal Counsel step-up]
→ cost_cap → compliance(LEGAL) → handle call.

Covers: AUTO read (L1), REVIEW write (L2), HOLD_FOR_REVIEW, HALT_UNRESOLVED_PROCESS,
REJECT_OUT_OF_SCOPE, HALT_REVIEW_DEFERRED, BLOCK_LOW_CONFIDENCE, 4×HALT_COST_CAP_BREACH,
HALT_COMPLIANCE_BLOCK, HALT_PROVIDER_ERROR, band boundaries, R-SEC constraints,
exactly-one-record invariant, and window accumulation.
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
from services.agents.contract_agent import (
    ContractAgent,
    ContractMask,
    CreateAgreementIntent,
    GetAgreementIntent,
    RecordSignatureIntent,
)
from services.agreement.agreement_port import (
    Agreement,
    AgreementError,
    AgreementStatus,
    CreateAgreementRequest,
    ProductType,
    SignAgreementRequest,
    SignatureStatus,
    TermsVersion,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


def _fake_agreement(agreement_id: str = "agr-001") -> Agreement:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return Agreement(
        agreement_id=agreement_id,
        customer_id="cust-001",
        product_type=ProductType.EMONEY_ACCOUNT,
        terms_version="1.0.0",
        status=AgreementStatus.SENT_FOR_SIGNATURE,
        signature_status=SignatureStatus.PENDING,
        created_at=now,
        updated_at=now,
        version_history=["1.0.0"],
    )


class FakeAgreementPort:
    """Synchronous stub satisfying the AgreementPort Protocol structurally."""

    def __init__(self, raise_error: bool = False) -> None:
        self._raise = raise_error
        self.create_calls: list[CreateAgreementRequest] = []
        self.signature_calls: list[SignAgreementRequest] = []
        self.get_calls: list[str] = []

    def create_agreement(self, req: CreateAgreementRequest) -> Agreement:
        if self._raise:
            raise AgreementError(code="CREATE_FAILED", message="fake domain error")
        self.create_calls.append(req)
        return _fake_agreement(f"agr-{len(self.create_calls):03d}")

    def record_signature(self, req: SignAgreementRequest) -> Agreement:
        if self._raise:
            raise AgreementError(code="SIGN_FAILED", message="fake signature error")
        self.signature_calls.append(req)
        return _fake_agreement(req.agreement_id)

    def get_agreement(self, agreement_id: str) -> Agreement:
        if self._raise:
            raise AgreementError(code="NOT_FOUND", message="agreement not found")
        self.get_calls.append(agreement_id)
        return _fake_agreement(agreement_id)

    def supersede(self, agreement_id: str, new_version: str, operator_id: str) -> Agreement:
        raise NotImplementedError

    def list_customer_agreements(self, customer_id: str) -> list[Agreement]:
        raise NotImplementedError

    def get_current_terms_version(self, product_type: ProductType) -> TermsVersion:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

_RESOLVED = ProcessRef(process_id="proc-001", version="1.0")
_UNRESOLVED = ProcessRef(process_id="", version="")


def _cap(
    *,
    max_req_tokens: int = 10_000,
    max_req_cost: str = "1.0",
    max_win_tokens: int = 100_000,
    max_win_cost: str = "100.0",
) -> CostCap:
    return CostCap(
        max_request_tokens=max_req_tokens,
        max_request_cost=Decimal(max_req_cost),
        max_window_tokens=max_win_tokens,
        max_window_cost=Decimal(max_win_cost),
    )


def make_mask(**overrides: object) -> ContractMask:
    defaults: dict[str, object] = {"cost_cap": _cap()}
    defaults.update(overrides)
    return ContractMask(**defaults)  # type: ignore[arg-type]


def make_agent(
    *,
    mask: ContractMask | None = None,
    raise_error: bool = False,
    cost_window: CostWindow | None = None,
) -> tuple[ContractAgent, FakeAgreementPort, FakeRecorder]:
    m = mask or make_mask()
    handle = FakeAgreementPort(raise_error=raise_error)
    rec = FakeRecorder()
    agent = ContractAgent(
        agreement_handle=handle,
        recorder=rec,
        mask=m,
        cost_window=cost_window,
    )
    return agent, handle, rec


def _cost(tokens: int = 100, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def create_intent(
    confidence: float = 0.95,
    *,
    process_ref: ProcessRef = _RESOLVED,
    customer_id: str = "cust-001",
    product_type: ProductType = ProductType.EMONEY_ACCOUNT,
    terms_version: str = "1.0.0",
) -> CreateAgreementIntent:
    return CreateAgreementIntent(
        intent_text="create agreement",
        process_ref=process_ref,
        customer_id=customer_id,
        product_type=product_type,
        terms_version=terms_version,
        correlation_id="corr-001",
        confidence_score=confidence,
        request_cost=_cost(),
    )


def sign_intent(
    confidence: float = 0.95,
    *,
    process_ref: ProcessRef = _RESOLVED,
    agreement_id: str = "agr-001",
    customer_id: str = "cust-001",
    signature_provider: str = "DocuSign",
    docusign_envelope_id: str | None = "env-001",
) -> RecordSignatureIntent:
    return RecordSignatureIntent(
        intent_text="record signature",
        process_ref=process_ref,
        agreement_id=agreement_id,
        customer_id=customer_id,
        signature_provider=signature_provider,
        docusign_envelope_id=docusign_envelope_id,
        correlation_id="corr-002",
        confidence_score=confidence,
        request_cost=_cost(),
    )


def get_intent(
    confidence: float = 0.95,
    *,
    process_ref: ProcessRef = _RESOLVED,
    agreement_id: str = "agr-001",
) -> GetAgreementIntent:
    return GetAgreementIntent(
        intent_text="get agreement",
        process_ref=process_ref,
        agreement_id=agreement_id,
        correlation_id="corr-003",
        confidence_score=confidence,
        request_cost=_cost(),
    )


# ---------------------------------------------------------------------------
# L1 AUTO read — get_agreement happy path
# ---------------------------------------------------------------------------


async def test_get_agreement_auto_executes() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.95))
    assert outcome.executed is True
    assert outcome.decision == ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert isinstance(outcome.result, Agreement)
    assert handle.get_calls == ["agr-001"]
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "GET_AGREEMENT"


async def test_get_agreement_auto_accumulates_window() -> None:
    window = CostWindow(window_ref="test:win")
    agent, _h, _r = make_agent(cost_window=window)
    await agent.get_agreement(get_intent(0.95))
    assert window.used_tokens == 100
    assert window.used_cost == Decimal("0.01")


async def test_get_agreement_auto_record_breach_flag_none() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    assert rec.records[0].budget_breach_flag == BudgetBreach.NONE


# ---------------------------------------------------------------------------
# L2 create_agreement — happy path (reviewer present)
# ---------------------------------------------------------------------------


async def test_create_agreement_with_reviewer_executes() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel-alice")
    assert outcome.executed is True
    assert outcome.decision == ConfirmationDecision.REVIEW
    assert outcome.halt_reason is None
    assert isinstance(outcome.result, Agreement)
    assert len(handle.create_calls) == 1
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "CREATE_AGREEMENT"
    assert rec.records[0].human_reviewed_by == "counsel-alice"


async def test_create_agreement_auto_confidence_stepped_up_to_review() -> None:
    # confidence=0.95 ≥ auto_threshold=0.90 → AUTO band, force_review=True → stepped to REVIEW
    agent, handle, _r = make_agent()
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel-alice")
    assert outcome.decision == ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert len(handle.create_calls) == 1


async def test_create_agreement_review_confidence_with_reviewer_executes() -> None:
    # confidence=0.80 (already REVIEW band) + force_review=True: no step-up needed
    agent, handle, _r = make_agent()
    outcome = await agent.create_agreement(create_intent(0.80), human_reviewed_by="counsel")
    assert outcome.executed is True
    assert outcome.decision == ConfirmationDecision.REVIEW
    assert len(handle.create_calls) == 1


async def test_create_agreement_accumulates_window_on_success() -> None:
    window = CostWindow(window_ref="test:win")
    agent, _h, _r = make_agent(cost_window=window)
    await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert window.used_tokens == 100
    assert window.used_cost == Decimal("0.01")


# ---------------------------------------------------------------------------
# L2 record_signature — happy path (reviewer present)
# ---------------------------------------------------------------------------


async def test_record_signature_with_reviewer_executes() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.record_signature(sign_intent(0.95), human_reviewed_by="counsel-bob")
    assert outcome.executed is True
    assert isinstance(outcome.result, Agreement)
    assert len(handle.signature_calls) == 1
    assert rec.records[0].action_taken == "RECORD_SIGNATURE"
    assert rec.records[0].human_reviewed_by == "counsel-bob"


async def test_record_signature_none_envelope_id_accepted() -> None:
    agent, handle, _r = make_agent()
    outcome = await agent.record_signature(
        sign_intent(0.95, docusign_envelope_id=None),
        human_reviewed_by="counsel-bob",
    )
    assert outcome.executed is True
    assert handle.signature_calls[0].docusign_envelope_id is None


# ---------------------------------------------------------------------------
# HOLD_FOR_REVIEW — L2 write without reviewer
# ---------------------------------------------------------------------------


async def test_create_agreement_no_reviewer_hold_for_review() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(create_intent(0.95))
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "LEGAL_COUNSEL"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "LEGAL_COUNSEL"
    assert handle.create_calls == []


async def test_record_signature_no_reviewer_hold_for_review() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.record_signature(sign_intent(0.95))
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.escalated_to == "LEGAL_COUNSEL"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert handle.signature_calls == []


async def test_hold_for_review_does_not_accumulate_window() -> None:
    window = CostWindow(window_ref="test:win")
    agent, _h, _r = make_agent(cost_window=window)
    await agent.create_agreement(create_intent(0.95))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_halt_unresolved_process_create() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(
        create_intent(0.95, process_ref=_UNRESOLVED), human_reviewed_by="counsel"
    )
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"
    assert handle.create_calls == []


async def test_halt_unresolved_process_get() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.95, process_ref=_UNRESOLVED))
    assert outcome.halt_reason == "unresolved_process_ref"
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"
    assert handle.get_calls == []


# ---------------------------------------------------------------------------
# REJECT_OUT_OF_SCOPE
# ---------------------------------------------------------------------------


async def test_reject_out_of_scope_op() -> None:
    mask = make_mask(scope=("OTHER.op",))
    agent, handle, rec = make_agent(mask=mask)
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert outcome.halt_reason == "out_of_scope"
    assert rec.records[0].action_taken == "REJECT_OUT_OF_SCOPE"
    assert handle.create_calls == []


# ---------------------------------------------------------------------------
# HALT_REVIEW_DEFERRED — get_agreement below AUTO band
# ---------------------------------------------------------------------------


async def test_get_agreement_review_band_halts_deferred() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.80))
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_REVIEW_DEFERRED"
    assert handle.get_calls == []


# ---------------------------------------------------------------------------
# BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence_create() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(create_intent(0.50), human_reviewed_by="counsel")
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert handle.create_calls == []


async def test_block_low_confidence_get() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.50))
    assert outcome.halt_reason == "low_confidence"
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert handle.get_calls == []


# ---------------------------------------------------------------------------
# Band boundary values
# ---------------------------------------------------------------------------


async def test_band_exactly_090_get_is_auto() -> None:
    """Score == auto_threshold: AUTO band; L1 read proceeds."""
    agent, handle, _r = make_agent()
    outcome = await agent.get_agreement(get_intent(0.90))
    assert outcome.decision == ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert handle.get_calls == ["agr-001"]


async def test_band_exactly_070_get_is_review_deferred() -> None:
    """Score == review_floor: REVIEW band; L1 read halts deferred."""
    agent, _h, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.70))
    assert outcome.decision == ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"
    assert rec.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_band_below_070_is_block() -> None:
    """Score < review_floor: BLOCK band."""
    agent, _h, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.69))
    assert outcome.decision == ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "low_confidence"


async def test_band_090_create_force_review_step_up_then_hold() -> None:
    """confidence=0.90 on create (force_review=True): AUTO→REVIEW, no reviewer → HOLD."""
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(create_intent(0.90))
    assert outcome.decision == ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "hitl_review_required"
    assert handle.create_calls == []


# ---------------------------------------------------------------------------
# HALT_COST_CAP_BREACH — 4 independent cost dimensions
# ---------------------------------------------------------------------------


async def test_halt_cost_cap_per_request_tokens() -> None:
    # request tokens (100) > max_request_tokens (50) → breach on condition 1
    mask = make_mask(cost_cap=_cap(max_req_tokens=50))
    agent, handle, rec = make_agent(mask=mask)
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert outcome.halt_reason == "cost_cap_breach"
    assert rec.records[0].action_taken == "HALT_COST_CAP_BREACH"
    assert rec.records[0].budget_breach_flag == BudgetBreach.BREACH
    assert handle.create_calls == []


async def test_halt_cost_cap_per_request_cost() -> None:
    # request cost (0.01) > max_request_cost (0.001) → breach on condition 2
    mask = make_mask(cost_cap=_cap(max_req_tokens=10_000, max_req_cost="0.001"))
    agent, handle, rec = make_agent(mask=mask)
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert outcome.halt_reason == "cost_cap_breach"
    assert handle.create_calls == []


async def test_halt_cost_cap_per_window_tokens() -> None:
    # window already 9_950; request adds 100 → 10_050 > 10_000 cap (condition 3)
    window = CostWindow(used_tokens=9_950, window_ref="test:win")
    mask = make_mask(cost_cap=_cap(max_win_tokens=10_000))
    agent, handle, rec = make_agent(mask=mask, cost_window=window)
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert outcome.halt_reason == "cost_cap_breach"
    assert handle.create_calls == []


async def test_halt_cost_cap_per_window_cost() -> None:
    # window already 0.995; request adds 0.01 → 1.005 > 1.0 cap (condition 4)
    window = CostWindow(used_cost=Decimal("0.995"), window_ref="test:win")
    mask = make_mask(cost_cap=_cap(max_win_cost="1.0"))
    agent, handle, rec = make_agent(mask=mask, cost_window=window)
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert outcome.halt_reason == "cost_cap_breach"
    assert handle.create_calls == []


# ---------------------------------------------------------------------------
# HALT_COMPLIANCE_BLOCK
# ---------------------------------------------------------------------------


async def test_halt_compliance_fail_blocks_and_escalates_to_legal_counsel() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(
        create_intent(0.95),
        human_reviewed_by="counsel",
        compliance_result=ComplianceResult.FAIL,
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "LEGAL_COUNSEL"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert rec.records[0].escalated_to == "LEGAL_COUNSEL"
    assert handle.create_calls == []


async def test_halt_compliance_escalate_also_blocks() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.create_agreement(
        create_intent(0.95),
        human_reviewed_by="counsel",
        compliance_result=ComplianceResult.ESCALATE,
    )
    assert outcome.halt_reason == "compliance_block"
    assert rec.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert handle.create_calls == []


async def test_halt_compliance_fail_on_get_agreement_auto_path() -> None:
    # Verifies the compliance gate fires on the AUTO-band L1 path too
    agent, handle, rec = make_agent()
    outcome = await agent.get_agreement(
        get_intent(0.95),
        compliance_result=ComplianceResult.FAIL,
    )
    assert outcome.halt_reason == "compliance_block"
    assert rec.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert handle.get_calls == []


async def test_compliance_na_passes_gate() -> None:
    """ComplianceResult.NA is treated as PASS — gate allows through."""
    agent, handle, _r = make_agent()
    outcome = await agent.create_agreement(
        create_intent(0.95),
        human_reviewed_by="counsel",
        compliance_result=ComplianceResult.NA,
    )
    assert outcome.executed is True
    assert len(handle.create_calls) == 1


# ---------------------------------------------------------------------------
# HALT_PROVIDER_ERROR — AgreementError from domain
# ---------------------------------------------------------------------------


async def test_provider_error_create_emits_record_then_reraises() -> None:
    agent, _h, rec = make_agent(raise_error=True)
    with pytest.raises(AgreementError):
        await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert len(rec.records) == 1
    r = rec.records[0]
    assert r.action_taken == "HALT_PROVIDER_ERROR:AgreementError"
    assert r.agent_id == "contract_agent"


async def test_provider_error_record_signature_emits_record_then_reraises() -> None:
    agent, _h, rec = make_agent(raise_error=True)
    with pytest.raises(AgreementError):
        await agent.record_signature(sign_intent(0.95), human_reviewed_by="counsel")
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "HALT_PROVIDER_ERROR:AgreementError"


async def test_provider_error_get_agreement_emits_record_then_reraises() -> None:
    agent, _h, rec = make_agent(raise_error=True)
    with pytest.raises(AgreementError):
        await agent.get_agreement(get_intent(0.95))
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "HALT_PROVIDER_ERROR:AgreementError"


async def test_provider_error_does_not_accumulate_window() -> None:
    window = CostWindow(window_ref="test:win")
    agent, _h, _r = make_agent(raise_error=True, cost_window=window)
    with pytest.raises(AgreementError):
        await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# Invalid confidence_score → ValueError (not a gate halt, no record)
# ---------------------------------------------------------------------------


async def test_confidence_above_one_raises_value_error() -> None:
    agent, _h, rec = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_agreement(get_intent(1.01))


async def test_confidence_below_zero_raises_value_error() -> None:
    agent, _h, rec = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_agreement(get_intent(-0.01))


# ---------------------------------------------------------------------------
# R-SEC constraints (ADR-021)
# ---------------------------------------------------------------------------


async def test_rsec_create_triggering_event_contains_customer_and_product_only() -> None:
    """triggering_event must use customer_id and product_type — never terms content."""
    agent, _h, rec = make_agent()
    await agent.create_agreement(
        create_intent(
            0.95,
            customer_id="cust-999",
            product_type=ProductType.FX_SERVICE,
            terms_version="2.3.0",
        ),
        human_reviewed_by="counsel",
    )
    ev = rec.records[0].triggering_event
    assert "cust-999" in ev
    assert "FX_SERVICE" in ev
    assert "2.3.0" not in ev  # terms_version MUST NOT appear (R-SEC)


async def test_rsec_record_signature_triggering_event_no_signature_data() -> None:
    """triggering_event for record_signature uses agreement_id only."""
    agent, _h, rec = make_agent()
    await agent.record_signature(
        sign_intent(
            0.95,
            agreement_id="agr-sec-001",
            signature_provider="DocuSign",
            docusign_envelope_id="env-secret-xyz",
        ),
        human_reviewed_by="counsel",
    )
    ev = rec.records[0].triggering_event
    assert "agr-sec-001" in ev
    assert "DocuSign" not in ev  # signature_provider MUST NOT appear
    assert "env-secret-xyz" not in ev  # envelope_id MUST NOT appear


async def test_rsec_get_agreement_triggering_event_uses_agreement_id() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95, agreement_id="agr-rsec-007"))
    ev = rec.records[0].triggering_event
    assert "agr-rsec-007" in ev
    assert ev.startswith("get_agreement:")


async def test_rsec_agreement_object_not_in_decision_record_create() -> None:
    """Agreement result MUST NOT appear in AgentDecisionRecord (ADR-046 R-SEC)."""
    agent, _h, rec = make_agent()
    outcome = await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert outcome.result is not None
    assert not hasattr(rec.records[0], "result")


async def test_rsec_agreement_object_not_in_decision_record_get() -> None:
    agent, _h, rec = make_agent()
    outcome = await agent.get_agreement(get_intent(0.95))
    assert outcome.result is not None
    assert not hasattr(rec.records[0], "result")


# ---------------------------------------------------------------------------
# Exactly-one-record invariant (ADR-046)
# ---------------------------------------------------------------------------


async def test_exactly_one_record_on_auto_get() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    assert len(rec.records) == 1


async def test_exactly_one_record_on_create_success() -> None:
    agent, _h, rec = make_agent()
    await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert len(rec.records) == 1


async def test_exactly_one_record_on_hold_for_review() -> None:
    agent, _h, rec = make_agent()
    await agent.create_agreement(create_intent(0.95))
    assert len(rec.records) == 1


async def test_exactly_one_record_on_compliance_block() -> None:
    agent, _h, rec = make_agent()
    await agent.create_agreement(
        create_intent(0.95),
        human_reviewed_by="counsel",
        compliance_result=ComplianceResult.FAIL,
    )
    assert len(rec.records) == 1


async def test_exactly_one_record_on_provider_error() -> None:
    agent, _h, rec = make_agent(raise_error=True)
    with pytest.raises(AgreementError):
        await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel")
    assert len(rec.records) == 1


# ---------------------------------------------------------------------------
# Lineage record fields
# ---------------------------------------------------------------------------


async def test_record_carries_correlation_id() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    assert rec.records[0].correlation_id == "corr-003"


async def test_record_carries_cost_dimensions() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    assert rec.records[0].cost_tokens == 100
    assert rec.records[0].cost_amount == Decimal("0.01")


async def test_record_id_unique_across_calls() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    await agent.get_agreement(get_intent(0.95))
    ids = [r.record_id for r in rec.records]
    assert len(set(ids)) == 2


async def test_success_reasoning_contains_reviewer_note_on_l2() -> None:
    agent, _h, rec = make_agent()
    await agent.create_agreement(create_intent(0.95), human_reviewed_by="counsel-alice")
    assert "counsel-alice" in rec.records[0].reasoning_summary


async def test_success_reasoning_no_reviewer_note_on_l1_auto() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    assert rec.records[0].human_reviewed_by is None
    assert "(reviewed by" not in rec.records[0].reasoning_summary


async def test_default_cost_window_ref_uses_agent_id() -> None:
    agent, _h, rec = make_agent()
    await agent.get_agreement(get_intent(0.95))
    assert rec.records[0].budget_window_ref == "contract_agent:default"
