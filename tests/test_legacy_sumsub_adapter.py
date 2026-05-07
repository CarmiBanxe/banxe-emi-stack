"""
tests/test_legacy_sumsub_adapter.py — REWRITE-4 LegacySumSubAdapter scaffold tests.

Coverage targets:
  - Module imports (no HTTP/TypeORM/gRPC/NestJS — I-02 transport-drop parity)
  - Protocol conformance (all 6 KYCWorkflowPort methods present)
  - create_workflow: INDIVIDUAL / BUSINESS happy paths
  - create_workflow: idempotency (same customer_id)
  - create_workflow: I-02 blocked jurisdiction (nationality + country_of_residence)
  - create_workflow: I-04 EDD thresholds (£10k individual / £50k corporate) + PEP flag
  - get_workflow: known / unknown workflow_id
  - submit_documents: happy path → DOCUMENT_REVIEW; wrong status; unknown workflow
  - approve_edd: happy path → APPROVED + mlro_sign_off; wrong status (I-27)
  - reject_workflow: from non-terminal; from terminal (guard)
  - advance_to: valid transition; illegal transition (state machine guard)
  - health(): returns True
  - Audit trail: CREATED event appended, record separate from KYCWorkflowResult (I-24)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.compliance.legacy.legacy_sumsub_adapter import (
    LegacySumSubAdapter,
    SumSubApplicationError,
    SumSubAuditRecord,
    SumSubWorkflowRecord,
)
from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _request(
    customer_id: str = "cust-001",
    kyc_type: KYCType = KYCType.INDIVIDUAL,
    nationality: str = "GB",
    country_of_residence: str = "GB",
    volume: Decimal = Decimal("5000.00"),
    is_pep: bool = False,
) -> KYCWorkflowRequest:
    return KYCWorkflowRequest(
        customer_id=customer_id,
        kyc_type=kyc_type,
        first_name="Alice",
        last_name="Smith",
        date_of_birth="1990-06-15",
        nationality=nationality,
        country_of_residence=country_of_residence,
        expected_transaction_volume=volume,
        is_pep=is_pep,
        business_name=None,
        registration_number=None,
    )


@pytest.fixture()
def adapter() -> LegacySumSubAdapter:
    return LegacySumSubAdapter()


# ── 1. No transport imports ────────────────────────────────────────────────────


def test_no_http_transport_imported() -> None:
    import sys

    import services.compliance.legacy.legacy_sumsub_adapter as mod

    for forbidden in ("httpx", "requests", "aiohttp", "axios"):
        assert forbidden not in sys.modules or mod.__name__ != forbidden


def test_no_db_transport_imported() -> None:
    import services.compliance.legacy.legacy_sumsub_adapter as mod

    src = mod.__file__ or ""
    with open(src) as f:
        import_lines = [
            ln for ln in f if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")
        ]
    import_block = " ".join(import_lines).lower()
    for forbidden in ("sqlalchemy", "typeorm", "motor", "pymongo", "asyncpg"):
        assert forbidden not in import_block, f"Forbidden DB transport imported: {forbidden}"


def test_no_queue_transport_imported() -> None:
    import services.compliance.legacy.legacy_sumsub_adapter as mod

    src = mod.__file__ or ""
    with open(src) as f:
        import_lines = [
            ln for ln in f if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")
        ]
    import_block = " ".join(import_lines).lower()
    for forbidden in ("rabbitmq", "aio_pika", "celery", "kafka"):
        assert forbidden not in import_block, f"Forbidden queue transport imported: {forbidden}"


# ── 2. Protocol conformance ────────────────────────────────────────────────────


def test_adapter_has_all_port_methods(adapter: LegacySumSubAdapter) -> None:
    for method in (
        "create_workflow",
        "get_workflow",
        "submit_documents",
        "approve_edd",
        "reject_workflow",
        "health",
    ):
        assert callable(getattr(adapter, method, None)), f"Missing port method: {method}"


def test_adapter_has_extra_methods(adapter: LegacySumSubAdapter) -> None:
    assert callable(getattr(adapter, "advance_to", None))
    assert callable(getattr(adapter, "collect_audit_records", None))


# ── 3. create_workflow — happy paths ──────────────────────────────────────────


def test_create_workflow_individual_returns_pending(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request())
    assert isinstance(result, KYCWorkflowResult)
    assert result.status == KYCStatus.PENDING
    assert result.kyc_type == KYCType.INDIVIDUAL
    assert result.customer_id == "cust-001"
    assert result.workflow_id.startswith("ssub-")


def test_create_workflow_business_returns_pending(adapter: LegacySumSubAdapter) -> None:
    req = _request(customer_id="biz-001", kyc_type=KYCType.BUSINESS, volume=Decimal("20000.00"))
    result = adapter.create_workflow(req)
    assert result.status == KYCStatus.PENDING
    assert result.kyc_type == KYCType.BUSINESS


def test_create_workflow_result_has_expiry(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request())
    delta = result.expires_at - result.created_at
    assert delta.days == 30


def test_create_workflow_edd_false_below_threshold(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request(volume=Decimal("9999.99")))
    assert result.edd_required is False


# ── 4. create_workflow — idempotency ──────────────────────────────────────────


def test_create_workflow_idempotent_same_customer(adapter: LegacySumSubAdapter) -> None:
    r1 = adapter.create_workflow(_request())
    r2 = adapter.create_workflow(_request())
    assert r1.workflow_id == r2.workflow_id


# ── 5. create_workflow — I-02 blocked jurisdictions ───────────────────────────


@pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"])
def test_create_workflow_blocked_nationality(adapter: LegacySumSubAdapter, country: str) -> None:
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.create_workflow(_request(nationality=country))
    assert exc_info.value.code == "blocked_jurisdiction"


def test_create_workflow_blocked_country_of_residence(adapter: LegacySumSubAdapter) -> None:
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.create_workflow(_request(country_of_residence="RU"))
    assert exc_info.value.code == "blocked_jurisdiction"


# ── 6. create_workflow — I-04 EDD thresholds ──────────────────────────────────


def test_create_workflow_individual_at_edd_threshold(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request(volume=Decimal("10000.00")))
    assert result.edd_required is True


def test_create_workflow_individual_below_edd_threshold(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request(volume=Decimal("9999.99")))
    assert result.edd_required is False


def test_create_workflow_business_at_edd_threshold(adapter: LegacySumSubAdapter) -> None:
    req = _request(customer_id="biz-002", kyc_type=KYCType.BUSINESS, volume=Decimal("50000.00"))
    result = adapter.create_workflow(req)
    assert result.edd_required is True


def test_create_workflow_business_below_edd_threshold(adapter: LegacySumSubAdapter) -> None:
    req = _request(customer_id="biz-003", kyc_type=KYCType.BUSINESS, volume=Decimal("49999.99"))
    result = adapter.create_workflow(req)
    assert result.edd_required is False


def test_create_workflow_pep_triggers_edd(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request(is_pep=True, volume=Decimal("100.00")))
    assert result.edd_required is True


# ── 7. get_workflow ────────────────────────────────────────────────────────────


def test_get_workflow_known_id(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request())
    fetched = adapter.get_workflow(created.workflow_id)
    assert fetched is not None
    assert fetched.workflow_id == created.workflow_id


def test_get_workflow_unknown_id_returns_none(adapter: LegacySumSubAdapter) -> None:
    result = adapter.get_workflow("ssub-nonexistent-999")
    assert result is None


# ── 8. submit_documents ────────────────────────────────────────────────────────


def test_submit_documents_transitions_to_document_review(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request())
    result = adapter.submit_documents(created.workflow_id, ["doc-passport-001", "doc-selfie-002"])
    assert result.status == KYCStatus.DOCUMENT_REVIEW


def test_submit_documents_wrong_status_raises(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request())
    adapter.submit_documents(created.workflow_id, ["doc-001"])
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.submit_documents(created.workflow_id, ["doc-002"])
    assert exc_info.value.code == "invalid_status_for_submit"


def test_submit_documents_unknown_workflow_raises(adapter: LegacySumSubAdapter) -> None:
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.submit_documents("ssub-ghost", ["doc-001"])
    assert exc_info.value.code == "workflow_not_found"


# ── 9. approve_edd (I-27 HITL gate) ───────────────────────────────────────────


def _workflow_at_mlro_review(adapter: LegacySumSubAdapter) -> str:
    req = _request(customer_id="pep-001", is_pep=True)
    created = adapter.create_workflow(req)
    adapter.submit_documents(created.workflow_id, ["doc-001"])
    adapter.advance_to(created.workflow_id, KYCStatus.RISK_ASSESSMENT)
    adapter.advance_to(created.workflow_id, KYCStatus.EDD_REQUIRED)
    adapter.advance_to(created.workflow_id, KYCStatus.MLRO_REVIEW)
    return created.workflow_id


def test_approve_edd_transitions_to_approved(adapter: LegacySumSubAdapter) -> None:
    wf_id = _workflow_at_mlro_review(adapter)
    result = adapter.approve_edd(wf_id, mlro_user_id="mlro-user-007")
    assert result.status == KYCStatus.APPROVED
    assert result.mlro_sign_off is True


def test_approve_edd_wrong_status_raises(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="cust-edd-wrong"))
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.approve_edd(created.workflow_id, mlro_user_id="mlro-007")
    assert exc_info.value.code == "invalid_status_for_approve_edd"


# ── 10. reject_workflow ────────────────────────────────────────────────────────


def test_reject_workflow_from_pending(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="cust-rej-01"))
    result = adapter.reject_workflow(created.workflow_id, RejectionReason.INCOMPLETE_DOCUMENTS)
    assert result.status == KYCStatus.REJECTED
    assert result.rejection_reason == RejectionReason.INCOMPLETE_DOCUMENTS


def test_reject_workflow_terminal_raises(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="cust-rej-02"))
    adapter.reject_workflow(created.workflow_id, RejectionReason.DOCUMENT_FRAUD)
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.reject_workflow(created.workflow_id, RejectionReason.AML_PATTERN)
    assert exc_info.value.code == "workflow_already_terminal"


# ── 11. advance_to — state machine ────────────────────────────────────────────


def test_advance_to_valid_transition(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="cust-adv-01"))
    adapter.submit_documents(created.workflow_id, ["doc-x"])
    record = adapter.advance_to(created.workflow_id, KYCStatus.RISK_ASSESSMENT, risk_score=42)
    assert isinstance(record, SumSubWorkflowRecord)
    assert record.status == KYCStatus.RISK_ASSESSMENT
    assert record.risk_score == 42


def test_advance_to_illegal_transition_raises(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="cust-adv-02"))
    with pytest.raises(SumSubApplicationError) as exc_info:
        adapter.advance_to(created.workflow_id, KYCStatus.APPROVED)
    assert exc_info.value.code == "invalid_state_transition"


def test_advance_to_appends_note(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="cust-adv-03"))
    adapter.submit_documents(created.workflow_id, ["doc-y"])
    record = adapter.advance_to(
        created.workflow_id, KYCStatus.RISK_ASSESSMENT, note="auto-risk-pass"
    )
    assert "auto-risk-pass" in record.notes


# ── 12. health ────────────────────────────────────────────────────────────────


def test_health_returns_true(adapter: LegacySumSubAdapter) -> None:
    assert adapter.health() is True


# ── 13. Audit trail (I-24) ────────────────────────────────────────────────────


def test_audit_created_event_appended(adapter: LegacySumSubAdapter) -> None:
    adapter.create_workflow(_request(customer_id="audit-001"))
    records = adapter.collect_audit_records()
    assert len(records) == 1
    assert records[0].event_type == "CREATED"
    assert records[0].status_from is None
    assert records[0].status_to == KYCStatus.PENDING


def test_audit_record_is_separate_from_result(adapter: LegacySumSubAdapter) -> None:
    result = adapter.create_workflow(_request(customer_id="audit-002"))
    audit = adapter.collect_audit_records()[0]
    assert isinstance(audit, SumSubAuditRecord)
    assert not isinstance(result, SumSubAuditRecord)
    assert audit.workflow_id == result.workflow_id


def test_audit_accumulates_across_transitions(adapter: LegacySumSubAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="audit-003"))
    adapter.submit_documents(created.workflow_id, ["doc-001"])
    records = adapter.collect_audit_records()
    assert len(records) == 2
    event_types = [r.event_type for r in records]
    assert "CREATED" in event_types
    assert "DOCUMENTS_SUBMITTED" in event_types


def test_collect_audit_records_returns_copy(adapter: LegacySumSubAdapter) -> None:
    adapter.create_workflow(_request(customer_id="audit-004"))
    copy1 = adapter.collect_audit_records()
    copy1.clear()
    copy2 = adapter.collect_audit_records()
    assert len(copy2) == 1
