"""
legacy_bkyc_adapter.py — LegacyBKYCAdapter implements KYCWorkflowPort (REWRITE-5).

Semantic rewrite of bkyc.service.ts (banxe-identity, 668L) — B2B/KYB workflow.
Transport dropped per ADR-025 §15-16:
  - TypeORM Repository (BKYCApplicationEntity, BKYCDocumentEntity)
  - RabbitMQ publishers (REQUEST_BANXE_COMPANY_CREATE, REQUEST_BANXE_COMPANY_UPDATE)
  - AbsLegalEntityConnector, AbsScoringConnector, DictionaryClientService
  - NestJS DI / @Injectable / @InjectRepository
  - lodash, class-transformer, uuid

Upstream TS method → KYCWorkflowPort mapping:
  createBKYCApplication(dto)          → create_workflow(request)          INITIATED
  submitCompanyInfo(id, dto)          → advance_step(id, COMPANY_INFO_SUBMITTED)
  submitUBODisclosure(id, ubos)       → advance_step(id, UBO_DISCLOSURE, ubos=...)
  submitDirectors(id, directors)      → advance_step(id, DIRECTOR_VERIFICATION, directors=...)
  submitDocuments(id, docs)           → submit_documents(id, docs)        DOCUMENT_REVIEW
  [mlro pickup]                       → advance_step(id, MLRO_REVIEW)
  acceptBKYCApplication(id, mlro_id)  → approve_edd(id, mlro_id)         APPROVED
  rejectBKYCApplication(id, reason)   → reject_workflow(id, reason)       REJECTED

Multi-step state machine:
  INITIATED           → COMPANY_INFO_SUBMITTED
  COMPANY_INFO_SUBMITTED → UBO_DISCLOSURE
  UBO_DISCLOSURE      → DIRECTOR_VERIFICATION
  DIRECTOR_VERIFICATION → DOCUMENT_REVIEW  (via submit_documents)
  DOCUMENT_REVIEW     → MLRO_REVIEW
  MLRO_REVIEW         → APPROVED (via approve_edd) | REJECTED

I-02: RU/BY/IR/KP/CU/MM/AF/VE/SY blocked at create_workflow on country_of_registration.
I-04 (corporate): EDD if expected_transaction_volume ≥ £50k OR any UBO is_pep=True
      OR any UBO ownership_percentage ≥ 25%. Re-evaluated at UBO_DISCLOSURE step.
I-24: BKYCAuditRecord append-only — never folded into KYCWorkflowResult.
I-27: approve_edd gated on current_step == MLRO_REVIEW AND edd_required=True.

Idempotency: raises duplicate_workflow for same customer_id with non-terminal workflow.
Canon: ADR-025 §15-16 + services.kyc.kyc_port + SESSION-2026-05-07-WAVE-D-KYC-START
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
import secrets
from typing import Literal

from pydantic import BaseModel

from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_BLOCKED_COUNTRIES: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)
_EDD_CORPORATE_THRESHOLD: Decimal = Decimal("50000.00")  # I-04 corporate
_UBO_SIGNIFICANT_OWNERSHIP: Decimal = Decimal("25.00")  # triggers EDD on single UBO
_UBO_MIN_DISCLOSURE_TOTAL: Decimal = Decimal("75.00")  # completeness guard
_WORKFLOW_TTL_DAYS: int = 30  # FCA MLR 2017
_MAX_BUSINESS_NAME_LEN: int = 200

_BKYCEventType = Literal[
    "CREATED",
    "COMPANY_INFO_SUBMITTED",
    "UBO_DISCLOSED",
    "DIRECTORS_SUBMITTED",
    "DOCUMENTS_SUBMITTED",
    "MLRO_REVIEW_STARTED",
    "APPROVED",
    "REJECTED",
]


class BKYCStep(str, Enum):
    INITIATED = "INITIATED"
    COMPANY_INFO_SUBMITTED = "COMPANY_INFO_SUBMITTED"
    UBO_DISCLOSURE = "UBO_DISCLOSURE"
    DIRECTOR_VERIFICATION = "DIRECTOR_VERIFICATION"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    MLRO_REVIEW = "MLRO_REVIEW"


_STEP_ORDER: list[BKYCStep] = [
    BKYCStep.INITIATED,
    BKYCStep.COMPANY_INFO_SUBMITTED,
    BKYCStep.UBO_DISCLOSURE,
    BKYCStep.DIRECTOR_VERIFICATION,
    BKYCStep.DOCUMENT_REVIEW,
    BKYCStep.MLRO_REVIEW,
]

_STEP_TO_STATUS: dict[BKYCStep, KYCStatus] = {
    BKYCStep.INITIATED: KYCStatus.PENDING,
    BKYCStep.COMPANY_INFO_SUBMITTED: KYCStatus.PENDING,
    BKYCStep.UBO_DISCLOSURE: KYCStatus.PENDING,
    BKYCStep.DIRECTOR_VERIFICATION: KYCStatus.PENDING,
    BKYCStep.DOCUMENT_REVIEW: KYCStatus.DOCUMENT_REVIEW,
    BKYCStep.MLRO_REVIEW: KYCStatus.MLRO_REVIEW,
}

_STEP_TO_EVENT: dict[BKYCStep, _BKYCEventType] = {
    BKYCStep.INITIATED: "CREATED",
    BKYCStep.COMPANY_INFO_SUBMITTED: "COMPANY_INFO_SUBMITTED",
    BKYCStep.UBO_DISCLOSURE: "UBO_DISCLOSED",
    BKYCStep.DIRECTOR_VERIFICATION: "DIRECTORS_SUBMITTED",
    BKYCStep.DOCUMENT_REVIEW: "DOCUMENTS_SUBMITTED",
    BKYCStep.MLRO_REVIEW: "MLRO_REVIEW_STARTED",
}

_TERMINAL_STATUSES: frozenset[KYCStatus] = frozenset(
    {KYCStatus.APPROVED, KYCStatus.REJECTED, KYCStatus.EXPIRED}
)


# ── Domain models ─────────────────────────────────────────────────────────────


class BKYCUBORecord(BaseModel, frozen=True):
    """Ultimate Beneficial Owner — shadows TS UboDto (TypeORM DROP)."""

    ubo_id: str
    full_name: str
    nationality: str
    date_of_birth: str
    ownership_percentage: Decimal
    is_pep: bool

    model_config = {"arbitrary_types_allowed": True}


class BKYCDirectorRecord(BaseModel, frozen=True):
    """Company director — shadows TS DirectorDto (TypeORM DROP)."""

    director_id: str
    full_name: str
    nationality: str
    role: str


class BKYCWorkflowRecord(BaseModel, frozen=True):
    """Internal domain record — shadows BKYCApplicationEntity (TypeORM DROP)."""

    workflow_id: str
    customer_id: str
    legal_entity_name: str
    legal_entity_type: str
    country_of_registration: str
    registration_number: str
    kyc_type: KYCType
    expected_transaction_volume: Decimal
    status: KYCStatus
    current_step: BKYCStep
    ubo_records: tuple[BKYCUBORecord, ...]
    directors: tuple[BKYCDirectorRecord, ...]
    document_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    risk_score: int | None
    edd_required: bool
    mlro_approved_by: str | None
    rejection_reason: RejectionReason | None
    notes: tuple[str, ...]

    model_config = {"arbitrary_types_allowed": True}


class BKYCAuditRecord(BaseModel, frozen=True):
    """Append-only audit event — I-24 compliance. Never folded into KYCWorkflowResult."""

    workflow_id: str
    customer_id: str
    event_type: _BKYCEventType
    step: BKYCStep | None
    occurred_at: datetime

    model_config = {"arbitrary_types_allowed": True}


# ── Error ─────────────────────────────────────────────────────────────────────


class BKYCApplicationError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_edd(volume: Decimal, ubo_records: tuple[BKYCUBORecord, ...]) -> bool:
    if volume >= _EDD_CORPORATE_THRESHOLD:
        return True
    return any(
        ubo.is_pep or ubo.ownership_percentage >= _UBO_SIGNIFICANT_OWNERSHIP for ubo in ubo_records
    )


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacyBKYCAdapter:
    """
    KYCWorkflowPort implementation — B2B/KYB multi-step workflow (REWRITE-5).

    Idempotency: raises duplicate_workflow for same customer_id with non-terminal workflow.
    In-memory; not durable or concurrency-safe. Production: Ballerine Wave E.
    """

    def __init__(self) -> None:
        self._by_workflow_id: dict[str, BKYCWorkflowRecord] = {}
        self._by_customer_id: dict[str, BKYCWorkflowRecord] = {}
        self._audit_log: list[BKYCAuditRecord] = []

    # ── KYCWorkflowPort ───────────────────────────────────────────────────────

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """createBKYCApplication() semantic — I-02 block, duplicate guard, INITIATED."""
        if not request.business_name or not request.business_name.strip():
            raise BKYCApplicationError(
                "business_name is required for B2B KYC", code="missing_business_name"
            )
        if len(request.business_name) > _MAX_BUSINESS_NAME_LEN:
            raise BKYCApplicationError(
                f"business_name exceeds {_MAX_BUSINESS_NAME_LEN} chars",
                code="business_name_too_long",
            )
        if not request.registration_number or not request.registration_number.strip():
            raise BKYCApplicationError(
                "registration_number is required for B2B KYC",
                code="missing_registration_number",
            )
        country = request.country_of_residence.upper()
        if country in _BLOCKED_COUNTRIES:
            raise BKYCApplicationError(
                f"Blocked jurisdiction: {country!r} (I-02)", code="blocked_jurisdiction"
            )
        existing = self._by_customer_id.get(request.customer_id)
        if existing is not None and existing.status not in _TERMINAL_STATUSES:
            raise BKYCApplicationError(
                f"Active workflow exists for customer {request.customer_id!r}",
                code="duplicate_workflow",
            )
        now = datetime.now(UTC)
        record = BKYCWorkflowRecord(
            workflow_id=f"bkyc-{secrets.token_hex(8)}",
            customer_id=request.customer_id,
            legal_entity_name=request.business_name,
            legal_entity_type="COMPANY",
            country_of_registration=country,
            registration_number=request.registration_number,
            kyc_type=request.kyc_type,
            expected_transaction_volume=request.expected_transaction_volume,
            status=KYCStatus.PENDING,
            current_step=BKYCStep.INITIATED,
            ubo_records=(),
            directors=(),
            document_ids=(),
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=_WORKFLOW_TTL_DAYS),
            risk_score=None,
            edd_required=request.expected_transaction_volume >= _EDD_CORPORATE_THRESHOLD,
            mlro_approved_by=None,
            rejection_reason=None,
            notes=(),
        )
        self._store(record)
        self._emit_audit(record, event_type="CREATED", step=BKYCStep.INITIATED)
        return self._to_result(record)

    def get_workflow(self, workflow_id: str) -> KYCWorkflowResult | None:
        record = self._by_workflow_id.get(workflow_id)
        return self._to_result(record) if record is not None else None

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        """submitDocuments() semantic — DIRECTOR_VERIFICATION → DOCUMENT_REVIEW."""
        record = self._require(workflow_id)
        if record.current_step != BKYCStep.DIRECTOR_VERIFICATION:
            raise BKYCApplicationError(
                f"submit_documents requires DIRECTOR_VERIFICATION step, got {record.current_step}",
                code="invalid_step_for_submit",
            )
        updated = record.model_copy(
            update={
                "status": KYCStatus.DOCUMENT_REVIEW,
                "current_step": BKYCStep.DOCUMENT_REVIEW,
                "document_ids": (*record.document_ids, *document_ids),
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(updated)
        self._emit_audit(updated, event_type="DOCUMENTS_SUBMITTED", step=BKYCStep.DOCUMENT_REVIEW)
        return self._to_result(updated)

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """acceptBKYCApplication() — MLRO_REVIEW → APPROVED (I-27 HITL gate)."""
        record = self._require(workflow_id)
        if record.current_step != BKYCStep.MLRO_REVIEW:
            raise BKYCApplicationError(
                f"approve_edd requires MLRO_REVIEW step, got {record.current_step}",
                code="invalid_step_for_approve",
            )
        if not record.edd_required:
            raise BKYCApplicationError(
                "approve_edd called but EDD is not required for this workflow",
                code="edd_not_required",
            )
        updated = record.model_copy(
            update={
                "status": KYCStatus.APPROVED,
                "mlro_approved_by": mlro_user_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(updated)
        self._emit_audit(updated, event_type="APPROVED", step=BKYCStep.MLRO_REVIEW)
        return self._to_result(updated)

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        """rejectBKYCApplication() — any non-terminal → REJECTED."""
        record = self._require(workflow_id)
        if record.status in _TERMINAL_STATUSES:
            raise BKYCApplicationError(
                f"Cannot reject terminal workflow (status={record.status})",
                code="workflow_already_terminal",
            )
        updated = record.model_copy(
            update={
                "status": KYCStatus.REJECTED,
                "rejection_reason": reason,
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(updated)
        self._emit_audit(updated, event_type="REJECTED", step=record.current_step)
        return self._to_result(updated)

    def health(self) -> bool:
        return True

    # ── Extra (beyond port) ───────────────────────────────────────────────────

    def advance_step(
        self,
        workflow_id: str,
        step: BKYCStep,
        *,
        ubo_records: list[BKYCUBORecord] | None = None,
        directors: list[BKYCDirectorRecord] | None = None,
        note: str | None = None,
    ) -> BKYCWorkflowRecord:
        """Drive the multi-step B2B state machine forward (sequential only)."""
        record = self._require(workflow_id)
        current_idx = _STEP_ORDER.index(record.current_step)
        target_idx = _STEP_ORDER.index(step)
        if target_idx != current_idx + 1:
            raise BKYCApplicationError(
                f"Illegal step transition: {record.current_step} → {step}",
                code="invalid_step_transition",
            )
        update: dict[str, object] = {
            "current_step": step,
            "status": _STEP_TO_STATUS[step],
            "updated_at": datetime.now(UTC),
        }
        if step == BKYCStep.UBO_DISCLOSURE and ubo_records is not None:
            ubo_tuple = tuple(ubo_records)
            total = sum(u.ownership_percentage for u in ubo_tuple)
            if total < _UBO_MIN_DISCLOSURE_TOTAL:
                raise BKYCApplicationError(
                    f"UBO disclosure incomplete: total ownership {total}% < 75%",
                    code="incomplete_ubo_disclosure",
                )
            update["ubo_records"] = ubo_tuple
            update["edd_required"] = _compute_edd(record.expected_transaction_volume, ubo_tuple)
        if step == BKYCStep.DIRECTOR_VERIFICATION and directors is not None:
            if len(directors) < 1:
                raise BKYCApplicationError("At least 1 director required", code="missing_directors")
            update["directors"] = tuple(directors)
        if note is not None:
            update["notes"] = (*record.notes, note)
        updated = record.model_copy(update=update)
        self._store(updated)
        self._emit_audit(updated, event_type=_STEP_TO_EVENT[step], step=step)
        return updated

    def collect_audit_records(self) -> list[BKYCAuditRecord]:
        """I-24 append-only audit trail — returns a copy."""
        return list(self._audit_log)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _require(self, workflow_id: str) -> BKYCWorkflowRecord:
        record = self._by_workflow_id.get(workflow_id)
        if record is None:
            raise BKYCApplicationError(
                f"Workflow not found: {workflow_id!r}", code="workflow_not_found"
            )
        return record

    def _store(self, record: BKYCWorkflowRecord) -> None:
        self._by_workflow_id[record.workflow_id] = record
        self._by_customer_id[record.customer_id] = record

    def _emit_audit(
        self,
        record: BKYCWorkflowRecord,
        *,
        event_type: _BKYCEventType,
        step: BKYCStep | None,
    ) -> None:
        self._audit_log.append(
            BKYCAuditRecord(
                workflow_id=record.workflow_id,
                customer_id=record.customer_id,
                event_type=event_type,
                step=step,
                occurred_at=datetime.now(UTC),
            )
        )

    def _to_result(self, record: BKYCWorkflowRecord) -> KYCWorkflowResult:
        return KYCWorkflowResult(
            workflow_id=record.workflow_id,
            customer_id=record.customer_id,
            status=record.status,
            kyc_type=record.kyc_type,
            created_at=record.created_at,
            updated_at=record.updated_at,
            expires_at=record.expires_at,
            edd_required=record.edd_required,
            rejection_reason=record.rejection_reason,
            risk_score=record.risk_score,
            notes=list(record.notes),
            mlro_sign_off=record.mlro_approved_by is not None,
        )
