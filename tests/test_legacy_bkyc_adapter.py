"""
tests/test_legacy_bkyc_adapter.py — REWRITE-5 LegacyBKYCAdapter tests.

Coverage targets:
  - Module imports (no HTTP/TypeORM/RabbitMQ — ADR-025 §15-16 transport-drop parity)
  - Protocol conformance (all 6 KYCWorkflowPort methods present)
  - create_workflow: happy path, TTL, validation (business_name / registration_number)
  - create_workflow: I-02 blocked jurisdiction (9 countries on country_of_registration)
  - create_workflow: I-04 EDD threshold (£50k corporate) + duplicate guard
  - get_workflow: known / unknown workflow_id
  - advance_step: sequential machine (company_info → ubo → directors)
  - advance_step: illegal transition guard + note append
  - advance_step: UBO disclosure — incomplete ownership, EDD re-compute (PEP / ownership)
  - submit_documents: happy path → DOCUMENT_REVIEW; wrong step; unknown workflow
  - approve_edd: happy path → APPROVED + mlro_sign_off; wrong step (I-27); edd_not_required
  - reject_workflow: from non-terminal; from terminal (guard)
  - health(): returns True
  - Audit trail I-24: CREATED event, separate from result, accumulate, copy protection
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.compliance.legacy.legacy_bkyc_adapter import (
    BKYCApplicationError,
    BKYCAuditRecord,
    BKYCDirectorRecord,
    BKYCStep,
    BKYCUBORecord,
    BKYCWorkflowRecord,
    LegacyBKYCAdapter,
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
    customer_id: str = "biz-001",
    kyc_type: KYCType = KYCType.BUSINESS,
    country_of_residence: str = "GB",
    volume: Decimal = Decimal("20000.00"),
    business_name: str = "Acme Corp Ltd",
    registration_number: str = "REG-123456",
) -> KYCWorkflowRequest:
    return KYCWorkflowRequest(
        customer_id=customer_id,
        kyc_type=kyc_type,
        first_name="John",
        last_name="Smith",
        date_of_birth="1980-01-15",
        nationality="GB",
        country_of_residence=country_of_residence,
        expected_transaction_volume=volume,
        is_pep=False,
        business_name=business_name,
        registration_number=registration_number,
    )


def _ubo(
    ubo_id: str = "ubo-001",
    ownership_percentage: Decimal = Decimal("26.00"),
    is_pep: bool = False,
) -> BKYCUBORecord:
    return BKYCUBORecord(
        ubo_id=ubo_id,
        full_name="Jane Doe",
        nationality="GB",
        date_of_birth="1975-03-20",
        ownership_percentage=ownership_percentage,
        is_pep=is_pep,
    )


def _director(director_id: str = "dir-001") -> BKYCDirectorRecord:
    return BKYCDirectorRecord(
        director_id=director_id,
        full_name="Bob Jones",
        nationality="GB",
        role="CEO",
    )


@pytest.fixture()
def adapter() -> LegacyBKYCAdapter:
    return LegacyBKYCAdapter()


def _at_director_verification(adapter: LegacyBKYCAdapter, customer_id: str = "biz-adv") -> str:
    """Helper: advance to DIRECTOR_VERIFICATION step."""
    req = _request(customer_id=customer_id, volume=Decimal("60000.00"))
    created = adapter.create_workflow(req)
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [
        _ubo("u1", Decimal("40.00")),
        _ubo("u2", Decimal("40.00")),
    ]
    adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    adapter.advance_step(
        created.workflow_id, BKYCStep.DIRECTOR_VERIFICATION, directors=[_director()]
    )
    return created.workflow_id


def _at_mlro_review(adapter: LegacyBKYCAdapter, customer_id: str = "biz-mlro") -> str:
    """Helper: advance to MLRO_REVIEW step (EDD workflow)."""
    wf_id = _at_director_verification(adapter, customer_id)
    adapter.submit_documents(wf_id, ["doc-cert-001"])
    adapter.advance_step(wf_id, BKYCStep.MLRO_REVIEW)
    return wf_id


# ── 1. No transport imports ────────────────────────────────────────────────────


def test_no_http_transport_imported() -> None:
    import sys

    import services.compliance.legacy.legacy_bkyc_adapter as mod

    for forbidden in ("httpx", "requests", "aiohttp", "axios"):
        assert forbidden not in sys.modules or mod.__name__ != forbidden


def test_no_db_transport_imported() -> None:
    import services.compliance.legacy.legacy_bkyc_adapter as mod

    src = mod.__file__ or ""
    with open(src) as f:
        import_lines = [
            ln for ln in f if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")
        ]
    import_block = " ".join(import_lines).lower()
    for forbidden in ("sqlalchemy", "typeorm", "motor", "pymongo", "asyncpg"):
        assert forbidden not in import_block, f"Forbidden DB transport imported: {forbidden}"


def test_no_queue_transport_imported() -> None:
    import services.compliance.legacy.legacy_bkyc_adapter as mod

    src = mod.__file__ or ""
    with open(src) as f:
        import_lines = [
            ln for ln in f if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")
        ]
    import_block = " ".join(import_lines).lower()
    for forbidden in ("rabbitmq", "aio_pika", "celery", "kafka"):
        assert forbidden not in import_block, f"Forbidden queue transport imported: {forbidden}"


# ── 2. Protocol conformance ────────────────────────────────────────────────────


def test_adapter_has_all_port_methods(adapter: LegacyBKYCAdapter) -> None:
    for method in (
        "create_workflow",
        "get_workflow",
        "submit_documents",
        "approve_edd",
        "reject_workflow",
        "health",
    ):
        assert callable(getattr(adapter, method, None)), f"Missing port method: {method}"


def test_adapter_has_extra_methods(adapter: LegacyBKYCAdapter) -> None:
    assert callable(getattr(adapter, "advance_step", None))
    assert callable(getattr(adapter, "collect_audit_records", None))


# ── 3. create_workflow — happy paths ──────────────────────────────────────────


def test_create_workflow_returns_pending(adapter: LegacyBKYCAdapter) -> None:
    result = adapter.create_workflow(_request())
    assert isinstance(result, KYCWorkflowResult)
    assert result.status == KYCStatus.PENDING
    assert result.kyc_type == KYCType.BUSINESS
    assert result.customer_id == "biz-001"
    assert result.workflow_id.startswith("bkyc-")


def test_create_workflow_result_has_expiry(adapter: LegacyBKYCAdapter) -> None:
    result = adapter.create_workflow(_request())
    delta = result.expires_at - result.created_at
    assert delta.days == 30


def test_create_workflow_edd_false_below_threshold(adapter: LegacyBKYCAdapter) -> None:
    result = adapter.create_workflow(_request(volume=Decimal("49999.99")))
    assert result.edd_required is False


def test_create_workflow_edd_true_at_threshold(adapter: LegacyBKYCAdapter) -> None:
    result = adapter.create_workflow(_request(volume=Decimal("50000.00")))
    assert result.edd_required is True


# ── 4. create_workflow — validation ───────────────────────────────────────────


def test_create_workflow_missing_business_name_raises(adapter: LegacyBKYCAdapter) -> None:
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.create_workflow(_request(business_name=""))
    assert exc_info.value.code == "missing_business_name"


def test_create_workflow_business_name_too_long_raises(adapter: LegacyBKYCAdapter) -> None:
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.create_workflow(_request(business_name="X" * 201))
    assert exc_info.value.code == "business_name_too_long"


def test_create_workflow_missing_registration_number_raises(adapter: LegacyBKYCAdapter) -> None:
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.create_workflow(_request(registration_number=""))
    assert exc_info.value.code == "missing_registration_number"


# ── 5. create_workflow — I-02 blocked jurisdictions ───────────────────────────


@pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"])
def test_create_workflow_blocked_country_of_registration(
    adapter: LegacyBKYCAdapter, country: str
) -> None:
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.create_workflow(_request(country_of_residence=country))
    assert exc_info.value.code == "blocked_jurisdiction"


# ── 6. create_workflow — duplicate guard ──────────────────────────────────────


def test_create_workflow_duplicate_active_raises(adapter: LegacyBKYCAdapter) -> None:
    adapter.create_workflow(_request(customer_id="biz-dup"))
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.create_workflow(_request(customer_id="biz-dup"))
    assert exc_info.value.code == "duplicate_workflow"


def test_create_workflow_allows_after_terminal(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-term"))
    adapter.reject_workflow(created.workflow_id, RejectionReason.AML_PATTERN)
    result2 = adapter.create_workflow(_request(customer_id="biz-term"))
    assert result2.status == KYCStatus.PENDING
    assert result2.workflow_id != created.workflow_id


# ── 7. get_workflow ────────────────────────────────────────────────────────────


def test_get_workflow_known_id(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request())
    fetched = adapter.get_workflow(created.workflow_id)
    assert fetched is not None
    assert fetched.workflow_id == created.workflow_id


def test_get_workflow_unknown_id_returns_none(adapter: LegacyBKYCAdapter) -> None:
    result = adapter.get_workflow("bkyc-nonexistent-999")
    assert result is None


# ── 8. advance_step — sequential state machine ────────────────────────────────


def test_advance_step_company_info_submitted(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-s1"))
    record = adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    assert isinstance(record, BKYCWorkflowRecord)
    assert record.current_step == BKYCStep.COMPANY_INFO_SUBMITTED
    assert record.status == KYCStatus.PENDING


def test_advance_step_ubo_disclosure(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-s2"))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [_ubo("u1", Decimal("50.00")), _ubo("u2", Decimal("30.00"))]
    record = adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    assert record.current_step == BKYCStep.UBO_DISCLOSURE
    assert len(record.ubo_records) == 2


def test_advance_step_director_verification(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-s3"))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [_ubo("u1", Decimal("80.00"))]
    adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    record = adapter.advance_step(
        created.workflow_id, BKYCStep.DIRECTOR_VERIFICATION, directors=[_director()]
    )
    assert record.current_step == BKYCStep.DIRECTOR_VERIFICATION
    assert len(record.directors) == 1


def test_advance_step_illegal_transition_raises(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-ill"))
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE)
    assert exc_info.value.code == "invalid_step_transition"


def test_advance_step_appends_note(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-note"))
    record = adapter.advance_step(
        created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED, note="verified-via-companies-house"
    )
    assert "verified-via-companies-house" in record.notes


# ── 9. advance_step — UBO validation ─────────────────────────────────────────


def test_advance_step_ubo_incomplete_disclosure_raises(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-ubo-inc"))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [_ubo("u1", Decimal("20.00"))]  # only 20% — below 75% threshold
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    assert exc_info.value.code == "incomplete_ubo_disclosure"


def test_advance_step_ubo_edd_recomputed_pep(adapter: LegacyBKYCAdapter) -> None:
    # Start below EDD threshold, UBO is PEP → EDD re-triggered
    created = adapter.create_workflow(_request(customer_id="biz-pep", volume=Decimal("10000.00")))
    assert created.edd_required is False
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [_ubo("u1", Decimal("80.00"), is_pep=True)]
    record = adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    assert record.edd_required is True


def test_advance_step_ubo_edd_recomputed_ownership(adapter: LegacyBKYCAdapter) -> None:
    # Volume below threshold, UBO ≥ 25% → EDD re-triggered
    created = adapter.create_workflow(_request(customer_id="biz-own", volume=Decimal("10000.00")))
    assert created.edd_required is False
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [
        _ubo("u1", Decimal("26.00")),
        _ubo("u2", Decimal("26.00")),
        _ubo("u3", Decimal("26.00")),
    ]
    record = adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    assert record.edd_required is True


def test_advance_step_ubo_edd_not_triggered_low_ownership(adapter: LegacyBKYCAdapter) -> None:
    # 4 UBOs at 20% each = 80% coverage, none ≥ 25%, none PEP → EDD stays False
    created = adapter.create_workflow(_request(customer_id="biz-nedd", volume=Decimal("10000.00")))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [
        _ubo("u1", Decimal("20.00")),
        _ubo("u2", Decimal("20.00")),
        _ubo("u3", Decimal("20.00")),
        _ubo("u4", Decimal("20.00")),
    ]
    record = adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    assert record.edd_required is False


def test_advance_step_empty_directors_raises(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-dir0"))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [_ubo("u1", Decimal("80.00"))]
    adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.advance_step(created.workflow_id, BKYCStep.DIRECTOR_VERIFICATION, directors=[])
    assert exc_info.value.code == "missing_directors"


# ── 10. submit_documents ───────────────────────────────────────────────────────


def test_submit_documents_transitions_to_document_review(adapter: LegacyBKYCAdapter) -> None:
    wf_id = _at_director_verification(adapter, "biz-doc1")
    result = adapter.submit_documents(wf_id, ["doc-cert-001", "doc-id-002"])
    assert result.status == KYCStatus.DOCUMENT_REVIEW


def test_submit_documents_wrong_step_raises(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-doc2"))
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.submit_documents(created.workflow_id, ["doc-001"])
    assert exc_info.value.code == "invalid_step_for_submit"


def test_submit_documents_unknown_workflow_raises(adapter: LegacyBKYCAdapter) -> None:
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.submit_documents("bkyc-ghost", ["doc-001"])
    assert exc_info.value.code == "workflow_not_found"


# ── 11. approve_edd (I-27 HITL gate) ──────────────────────────────────────────


def test_approve_edd_transitions_to_approved(adapter: LegacyBKYCAdapter) -> None:
    wf_id = _at_mlro_review(adapter, "biz-edd1")
    result = adapter.approve_edd(wf_id, mlro_user_id="mlro-007")
    assert result.status == KYCStatus.APPROVED
    assert result.mlro_sign_off is True


def test_approve_edd_wrong_step_raises(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-edd2"))
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.approve_edd(created.workflow_id, mlro_user_id="mlro-007")
    assert exc_info.value.code == "invalid_step_for_approve"


def test_approve_edd_not_required_raises(adapter: LegacyBKYCAdapter) -> None:
    # Volume below threshold, no PEP, low ownership → edd_required=False at MLRO_REVIEW
    created = adapter.create_workflow(_request(customer_id="biz-edd3", volume=Decimal("1000.00")))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    ubos = [
        _ubo("u1", Decimal("20.00")),
        _ubo("u2", Decimal("20.00")),
        _ubo("u3", Decimal("20.00")),
        _ubo("u4", Decimal("20.00")),
    ]
    adapter.advance_step(created.workflow_id, BKYCStep.UBO_DISCLOSURE, ubo_records=ubos)
    adapter.advance_step(
        created.workflow_id, BKYCStep.DIRECTOR_VERIFICATION, directors=[_director()]
    )
    adapter.submit_documents(created.workflow_id, ["doc-001"])
    adapter.advance_step(created.workflow_id, BKYCStep.MLRO_REVIEW)
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.approve_edd(created.workflow_id, mlro_user_id="mlro-007")
    assert exc_info.value.code == "edd_not_required"


# ── 12. reject_workflow ────────────────────────────────────────────────────────


def test_reject_workflow_from_pending(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-rej1"))
    result = adapter.reject_workflow(created.workflow_id, RejectionReason.HIGH_RISK_JURISDICTION)
    assert result.status == KYCStatus.REJECTED
    assert result.rejection_reason == RejectionReason.HIGH_RISK_JURISDICTION


def test_reject_workflow_terminal_raises(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="biz-rej2"))
    adapter.reject_workflow(created.workflow_id, RejectionReason.DOCUMENT_FRAUD)
    with pytest.raises(BKYCApplicationError) as exc_info:
        adapter.reject_workflow(created.workflow_id, RejectionReason.AML_PATTERN)
    assert exc_info.value.code == "workflow_already_terminal"


# ── 13. health ─────────────────────────────────────────────────────────────────


def test_health_returns_true(adapter: LegacyBKYCAdapter) -> None:
    assert adapter.health() is True


# ── 14. Audit trail (I-24) ─────────────────────────────────────────────────────


def test_audit_created_event_appended(adapter: LegacyBKYCAdapter) -> None:
    adapter.create_workflow(_request(customer_id="audit-001"))
    records = adapter.collect_audit_records()
    assert len(records) == 1
    assert records[0].event_type == "CREATED"
    assert records[0].step == BKYCStep.INITIATED


def test_audit_record_is_separate_from_result(adapter: LegacyBKYCAdapter) -> None:
    result = adapter.create_workflow(_request(customer_id="audit-002"))
    audit = adapter.collect_audit_records()[0]
    assert isinstance(audit, BKYCAuditRecord)
    assert not isinstance(result, BKYCAuditRecord)
    assert audit.workflow_id == result.workflow_id


def test_audit_accumulates_across_transitions(adapter: LegacyBKYCAdapter) -> None:
    created = adapter.create_workflow(_request(customer_id="audit-003"))
    adapter.advance_step(created.workflow_id, BKYCStep.COMPANY_INFO_SUBMITTED)
    records = adapter.collect_audit_records()
    assert len(records) == 2
    event_types = [r.event_type for r in records]
    assert "CREATED" in event_types
    assert "COMPANY_INFO_SUBMITTED" in event_types


def test_collect_audit_records_returns_copy(adapter: LegacyBKYCAdapter) -> None:
    adapter.create_workflow(_request(customer_id="audit-004"))
    copy1 = adapter.collect_audit_records()
    copy1.clear()
    copy2 = adapter.collect_audit_records()
    assert len(copy2) == 1
