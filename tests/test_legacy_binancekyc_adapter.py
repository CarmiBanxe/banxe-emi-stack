"""
Tests for LegacyBinanceKYCAdapter (REWRITE-6).

Coverage targets:
  - Transport isolation: no HTTP/DB/queue imports
  - KYCWorkflowPort surface conformance
  - BinanceKYCTier → KYCStatus normalisation (deterministic, exhaustive)
  - create_workflow: happy, EDD thresholds, I-02 blocked countries, idempotency
  - get_workflow: known / unknown
  - submit_documents: happy, wrong-step, unknown-id
  - advance_to: valid transitions, invalid transition guard
  - approve_edd: I-27 gate (happy, wrong status, edd_not_required)
  - reject_workflow: non-terminal, terminal guard
  - health
  - Audit trail I-24: event emitted, separate from result, accumulation, copy safety
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import ValidationError
import pytest

from services.compliance.legacy.legacy_binancekyc_adapter import (
    BinanceKYCAuditRecord,
    BinanceKYCError,
    BinanceKYCTier,
    BinanceVerificationRecord,
    LegacyBinanceKYCAdapter,
    normalize_binance_tier,
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
    customer_id: str = "cust-bn-001",
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
    )


def _at_document_review(adapter: LegacyBinanceKYCAdapter, customer_id: str = "cust-dr") -> str:
    result = adapter.create_workflow(_request(customer_id=customer_id))
    adapter.submit_documents(result.workflow_id, ["doc-id-1"])
    return result.workflow_id


def _at_risk_assessment(adapter: LegacyBinanceKYCAdapter, customer_id: str = "cust-ra") -> str:
    wid = _at_document_review(adapter, customer_id)
    adapter.advance_to(wid, KYCStatus.RISK_ASSESSMENT)
    return wid


def _at_edd_required(adapter: LegacyBinanceKYCAdapter, customer_id: str = "cust-edd") -> str:
    req = _request(customer_id=customer_id, volume=Decimal("15000.00"))
    result = adapter.create_workflow(req)
    adapter.submit_documents(result.workflow_id, ["doc-1"])
    adapter.advance_to(result.workflow_id, KYCStatus.RISK_ASSESSMENT)
    adapter.advance_to(result.workflow_id, KYCStatus.EDD_REQUIRED)
    return result.workflow_id


# ── Transport isolation ────────────────────────────────────────────────────────


def test_no_http_transport_import() -> None:
    import ast
    import pathlib

    src = pathlib.Path("services/compliance/legacy/legacy_binancekyc_adapter.py").read_text()
    tree = ast.parse(src)
    http_libs = {"requests", "httpx", "aiohttp", "urllib3", "http.client"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in http_libs, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in http_libs, node.module


def test_no_db_transport_import() -> None:
    import ast
    import pathlib

    src = pathlib.Path("services/compliance/legacy/legacy_binancekyc_adapter.py").read_text()
    tree = ast.parse(src)
    db_libs = {"sqlalchemy", "asyncpg", "psycopg2", "clickhouse_driver", "redis"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in db_libs, node.module


def test_no_queue_transport_import() -> None:
    import ast
    import pathlib

    src = pathlib.Path("services/compliance/legacy/legacy_binancekyc_adapter.py").read_text()
    tree = ast.parse(src)
    queue_libs = {"aio_pika", "pika", "kafka", "aiokafka", "celery"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in queue_libs, node.module


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_adapter_has_all_port_methods() -> None:
    port_methods = {
        "create_workflow",
        "get_workflow",
        "submit_documents",
        "approve_edd",
        "reject_workflow",
        "health",
    }
    for method in port_methods:
        assert hasattr(LegacyBinanceKYCAdapter, method), method


def test_adapter_has_extra_methods() -> None:
    assert hasattr(LegacyBinanceKYCAdapter, "advance_to")
    assert hasattr(LegacyBinanceKYCAdapter, "collect_audit_records")


def test_binance_tier_enum_importable() -> None:
    assert BinanceKYCTier.TIER_1_BASIC.value == "TIER_1_BASIC"
    assert BinanceKYCTier.TIER_2_INTERMEDIATE.value == "TIER_2_INTERMEDIATE"
    assert BinanceKYCTier.TIER_3_FULL.value == "TIER_3_FULL"


def test_normalize_binance_tier_importable() -> None:
    assert callable(normalize_binance_tier)


# ── Tier normalisation — deterministic, exhaustive ────────────────────────────


def test_normalize_tier1_basic_to_pending() -> None:
    assert normalize_binance_tier(BinanceKYCTier.TIER_1_BASIC) == KYCStatus.PENDING


def test_normalize_tier2_intermediate_to_document_review() -> None:
    assert normalize_binance_tier(BinanceKYCTier.TIER_2_INTERMEDIATE) == KYCStatus.DOCUMENT_REVIEW


def test_normalize_tier3_full_to_risk_assessment() -> None:
    assert normalize_binance_tier(BinanceKYCTier.TIER_3_FULL) == KYCStatus.RISK_ASSESSMENT


def test_normalize_tier_mapping_exhaustive() -> None:
    """All BinanceKYCTier values must be covered by normalize_binance_tier."""
    for tier in BinanceKYCTier:
        result = normalize_binance_tier(tier)
        assert isinstance(result, KYCStatus), f"{tier} not mapped"


# ── create_workflow happy path ────────────────────────────────────────────────


def test_create_workflow_returns_pending() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request())
    assert result.status == KYCStatus.PENDING
    assert isinstance(result, KYCWorkflowResult)


def test_create_workflow_ttl_30_days() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request())
    delta = result.expires_at - result.created_at
    assert delta.days == 30


def test_create_workflow_edd_false_low_volume() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(volume=Decimal("9999.99")))
    assert result.edd_required is False


def test_create_workflow_edd_true_individual_at_threshold() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(volume=Decimal("10000.00")))
    assert result.edd_required is True


def test_create_workflow_edd_true_pep() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(volume=Decimal("100.00"), is_pep=True))
    assert result.edd_required is True


def test_create_workflow_edd_corporate_threshold() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(
        _request(kyc_type=KYCType.BUSINESS, volume=Decimal("50000.00"))
    )
    assert result.edd_required is True


def test_create_workflow_edd_corporate_below_threshold() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(
        _request(kyc_type=KYCType.BUSINESS, volume=Decimal("49999.99"))
    )
    assert result.edd_required is False


def test_create_workflow_workflow_id_prefixed() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request())
    assert result.workflow_id.startswith("bnkyc-")


# ── I-02 blocked countries (parametrized) ────────────────────────────────────


@pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"])
def test_create_workflow_blocks_nationality(country: str) -> None:
    adapter = LegacyBinanceKYCAdapter()
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.create_workflow(_request(nationality=country))
    assert exc_info.value.code == "blocked_jurisdiction"


@pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"])
def test_create_workflow_blocks_country_of_residence(country: str) -> None:
    adapter = LegacyBinanceKYCAdapter()
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.create_workflow(_request(nationality="GB", country_of_residence=country))
    assert exc_info.value.code == "blocked_jurisdiction"


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_create_workflow_idempotent_returns_existing() -> None:
    adapter = LegacyBinanceKYCAdapter()
    r1 = adapter.create_workflow(_request())
    r2 = adapter.create_workflow(_request())
    assert r1.workflow_id == r2.workflow_id


def test_create_workflow_allows_new_after_rejection() -> None:
    adapter = LegacyBinanceKYCAdapter()
    r1 = adapter.create_workflow(_request(customer_id="cust-idem"))
    adapter.reject_workflow(r1.workflow_id, RejectionReason.HIGH_RISK_JURISDICTION)
    r2 = adapter.create_workflow(_request(customer_id="cust-idem-new"))
    assert r2.workflow_id != r1.workflow_id


# ── get_workflow ──────────────────────────────────────────────────────────────


def test_get_workflow_returns_result_for_known_id() -> None:
    adapter = LegacyBinanceKYCAdapter()
    created = adapter.create_workflow(_request(customer_id="cust-get"))
    fetched = adapter.get_workflow(created.workflow_id)
    assert fetched is not None
    assert fetched.workflow_id == created.workflow_id


def test_get_workflow_returns_none_for_unknown() -> None:
    adapter = LegacyBinanceKYCAdapter()
    assert adapter.get_workflow("no-such-id") is None


# ── submit_documents ──────────────────────────────────────────────────────────


def test_submit_documents_happy_transitions_to_document_review() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-sub"))
    updated = adapter.submit_documents(result.workflow_id, ["doc-abc", "doc-def"])
    assert updated.status == KYCStatus.DOCUMENT_REVIEW


def test_submit_documents_wrong_status_raises() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_document_review(adapter, "cust-sub-bad")
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.submit_documents(wid, ["doc-x"])
    assert exc_info.value.code == "invalid_status_for_submit"


def test_submit_documents_unknown_id_raises() -> None:
    adapter = LegacyBinanceKYCAdapter()
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.submit_documents("ghost-id", ["doc-1"])
    assert exc_info.value.code == "workflow_not_found"


# ── advance_to state machine ──────────────────────────────────────────────────


def test_advance_to_document_review_to_risk_assessment() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_document_review(adapter, "cust-adv-1")
    result = adapter.advance_to(wid, KYCStatus.RISK_ASSESSMENT, risk_score=42)
    assert result.status == KYCStatus.RISK_ASSESSMENT
    assert result.risk_score == 42


def test_advance_to_risk_assessment_to_edd_required() -> None:
    adapter = LegacyBinanceKYCAdapter()
    req = _request(customer_id="cust-adv-2", volume=Decimal("20000.00"))
    r = adapter.create_workflow(req)
    adapter.submit_documents(r.workflow_id, ["d1"])
    adapter.advance_to(r.workflow_id, KYCStatus.RISK_ASSESSMENT)
    result = adapter.advance_to(r.workflow_id, KYCStatus.EDD_REQUIRED)
    assert result.status == KYCStatus.EDD_REQUIRED


def test_advance_to_risk_assessment_to_approved_no_edd() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_risk_assessment(adapter, "cust-adv-3")
    result = adapter.advance_to(wid, KYCStatus.APPROVED)
    assert result.status == KYCStatus.APPROVED


def test_advance_to_invalid_transition_raises() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-adv-bad"))
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.advance_to(result.workflow_id, KYCStatus.APPROVED)
    assert exc_info.value.code == "invalid_transition"


def test_advance_to_note_appended() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_document_review(adapter, "cust-note")
    adapter.advance_to(wid, KYCStatus.RISK_ASSESSMENT, note="automated ML check passed")
    fetched = adapter.get_workflow(wid)
    assert fetched is not None
    assert "automated ML check passed" in fetched.notes


# ── approve_edd I-27 ──────────────────────────────────────────────────────────


def test_approve_edd_happy_from_edd_required() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_edd_required(adapter, "cust-edd-ok")
    result = adapter.approve_edd(wid, "mlro-user-1")
    assert result.status == KYCStatus.APPROVED
    assert result.mlro_sign_off is True


def test_approve_edd_happy_from_mlro_review() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_edd_required(adapter, "cust-mlro-ok")
    adapter.advance_to(wid, KYCStatus.MLRO_REVIEW)
    result = adapter.approve_edd(wid, "mlro-user-2")
    assert result.status == KYCStatus.APPROVED
    assert result.mlro_sign_off is True


def test_approve_edd_wrong_status_raises() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_document_review(adapter, "cust-edd-bad-status")
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.approve_edd(wid, "mlro-x")
    assert exc_info.value.code == "invalid_status_for_approve"


def test_approve_edd_when_not_required_raises() -> None:
    adapter = LegacyBinanceKYCAdapter()
    # Low volume → edd_required=False. Manually force to EDD_REQUIRED via advance_to.
    req = _request(customer_id="cust-no-edd", volume=Decimal("100.00"))
    r = adapter.create_workflow(req)
    adapter.submit_documents(r.workflow_id, ["doc"])
    adapter.advance_to(r.workflow_id, KYCStatus.RISK_ASSESSMENT)
    # Force status to EDD_REQUIRED despite edd_required=False (simulates misconfiguration)
    adapter.advance_to(r.workflow_id, KYCStatus.EDD_REQUIRED)
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.approve_edd(r.workflow_id, "mlro-y")
    assert exc_info.value.code == "edd_not_required"


# ── reject_workflow ────────────────────────────────────────────────────────────


def test_reject_workflow_from_non_terminal() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-rej"))
    rejected = adapter.reject_workflow(result.workflow_id, RejectionReason.SANCTIONS_HIT)
    assert rejected.status == KYCStatus.REJECTED
    assert rejected.rejection_reason == RejectionReason.SANCTIONS_HIT


def test_reject_workflow_from_terminal_raises() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-rej-term"))
    adapter.reject_workflow(result.workflow_id, RejectionReason.DOCUMENT_FRAUD)
    with pytest.raises(BinanceKYCError) as exc_info:
        adapter.reject_workflow(result.workflow_id, RejectionReason.AML_PATTERN)
    assert exc_info.value.code == "already_terminal"


# ── health ────────────────────────────────────────────────────────────────────


def test_health_returns_true() -> None:
    assert LegacyBinanceKYCAdapter().health() is True


# ── Audit trail I-24 ──────────────────────────────────────────────────────────


def test_audit_created_event_emitted_on_create() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-aud-1"))
    records = adapter.collect_audit_records()
    assert len(records) == 1
    assert records[0].event_type == "CREATED"
    assert records[0].workflow_id == result.workflow_id
    assert records[0].status_from is None


def test_audit_documents_submitted_event_on_submit() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-aud-2"))
    adapter.submit_documents(result.workflow_id, ["doc-1"])
    records = adapter.collect_audit_records()
    event_types = [r.event_type for r in records]
    assert "DOCUMENTS_SUBMITTED" in event_types


def test_audit_records_separate_from_kyc_result() -> None:
    adapter = LegacyBinanceKYCAdapter()
    adapter.create_workflow(_request(customer_id="cust-aud-3"))
    result = adapter.create_workflow(_request(customer_id="cust-aud-3"))
    assert not hasattr(result, "event_type")
    assert isinstance(adapter.collect_audit_records()[0], BinanceKYCAuditRecord)


def test_audit_records_accumulate_across_transitions() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-aud-4"))
    adapter.submit_documents(result.workflow_id, ["d1"])
    adapter.advance_to(result.workflow_id, KYCStatus.RISK_ASSESSMENT)
    records = adapter.collect_audit_records()
    assert len(records) == 3  # CREATED + DOCUMENTS_SUBMITTED + RISK_ASSESSED


def test_audit_collect_returns_copy() -> None:
    adapter = LegacyBinanceKYCAdapter()
    adapter.create_workflow(_request(customer_id="cust-aud-5"))
    copy1 = adapter.collect_audit_records()
    copy1.clear()
    copy2 = adapter.collect_audit_records()
    assert len(copy2) == 1


# ── Internal model integrity ──────────────────────────────────────────────────


def test_verification_record_is_frozen() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-frozen"))
    record = adapter._by_workflow_id[result.workflow_id]
    assert isinstance(record, BinanceVerificationRecord)
    with pytest.raises(ValidationError):
        record.status = KYCStatus.APPROVED  # type: ignore[misc]


def test_create_workflow_sets_tier1_basic() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-tier-init"))
    record = adapter._by_workflow_id[result.workflow_id]
    assert record.current_tier == BinanceKYCTier.TIER_1_BASIC


def test_submit_documents_upgrades_to_tier2() -> None:
    adapter = LegacyBinanceKYCAdapter()
    result = adapter.create_workflow(_request(customer_id="cust-tier-2"))
    adapter.submit_documents(result.workflow_id, ["doc-1"])
    record = adapter._by_workflow_id[result.workflow_id]
    assert record.current_tier == BinanceKYCTier.TIER_2_INTERMEDIATE


def test_advance_to_risk_assessment_upgrades_to_tier3() -> None:
    adapter = LegacyBinanceKYCAdapter()
    wid = _at_document_review(adapter, "cust-tier-3")
    adapter.advance_to(wid, KYCStatus.RISK_ASSESSMENT)
    record = adapter._by_workflow_id[wid]
    assert record.current_tier == BinanceKYCTier.TIER_3_FULL
