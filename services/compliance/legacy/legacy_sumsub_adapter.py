"""
legacy_sumsub_adapter.py — LegacySumSubAdapter implements KYCWorkflowPort (REWRITE-4).

Semantic rewrite of sumsub-connector.service.ts (banxe-identity, 979L) +
sumsub-connector-applicant.service.ts (490L).
Transport dropped per ADR-025 §15-16:
  - SumsubClient HMAC-signed axios HTTP
  - TypeORM (UserIdentityDocEntity, SumsubConfigEntity, AvailableErc20TokenForSumsubEntity)
  - GrpcCompaniesConnector, GrpcAddressesConnector, AbsLegalEntityConnector
  - NestJS DI / @Injectable / @InjectRepository
  - RabbitMQ publishers
  - Amplitude analytics
  - ConfigService (SUMSUB_SOURCE_KEY)

Upstream TS method → KYCWorkflowPort mapping:
  createApplicant(dto)         → create_workflow(request)       PENDING
  submitUserDocuments(payload) → submit_documents(id, docs)     DOCUMENT_REVIEW
  [applicantReviewed webhook]  → advance_to(id, status)         RISK_ASSESSMENT / REJECTED
  [EDD path]                   → advance_to(id, EDD_REQUIRED)   EDD_REQUIRED
  [MLRO pickup]                → advance_to(id, MLRO_REVIEW)    MLRO_REVIEW
  approveApplicant / MLRO      → approve_edd(id, mlro_id)       APPROVED
  declineApplicant(id, reason) → reject_workflow(id, reason)    REJECTED

State machine:
  PENDING         → DOCUMENT_REVIEW | REJECTED | EXPIRED
  DOCUMENT_REVIEW → RISK_ASSESSMENT | REJECTED | EXPIRED
  RISK_ASSESSMENT → EDD_REQUIRED    | APPROVED  | REJECTED
  EDD_REQUIRED    → MLRO_REVIEW     | REJECTED
  MLRO_REVIEW     → APPROVED        | REJECTED
  APPROVED / REJECTED / EXPIRED → (terminal)

I-02: RU/BY/IR/KP/CU/MM/AF/VE/SY blocked at create_workflow → HIGH_RISK_JURISDICTION.
I-04: EDD if expected_transaction_volume ≥ £10k (INDIVIDUAL) / £50k (BUSINESS/SOLE_TRADER).
I-24: SumSubAuditRecord append-only — never folded into KYCWorkflowResult.

Idempotency: keyed by customer_id — one active workflow per customer.
Canon: ADR-025 §15-16 + services.kyc.kyc_port + SESSION-2026-05-07-WAVE-D-KYC-START
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from services.shared.errors import BanxeLegacyAdapterError

# ── Constants ─────────────────────────────────────────────────────────────────

_BLOCKED_COUNTRIES: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)
_EDD_INDIVIDUAL_THRESHOLD: Decimal = Decimal("10000.00")  # I-04
_EDD_CORPORATE_THRESHOLD: Decimal = Decimal("50000.00")  # I-04
_WORKFLOW_TTL_DAYS: int = 30  # FCA MLR 2017

_SumSubEventType = Literal[
    "CREATED",
    "DOCUMENTS_SUBMITTED",
    "RISK_ASSESSED",
    "EDD_TRIGGERED",
    "MLRO_REVIEW_STARTED",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
]

_VALID_TRANSITIONS: dict[KYCStatus, frozenset[KYCStatus]] = {
    KYCStatus.PENDING: frozenset(
        {KYCStatus.DOCUMENT_REVIEW, KYCStatus.REJECTED, KYCStatus.EXPIRED}
    ),
    KYCStatus.DOCUMENT_REVIEW: frozenset(
        {KYCStatus.RISK_ASSESSMENT, KYCStatus.REJECTED, KYCStatus.EXPIRED}
    ),
    KYCStatus.RISK_ASSESSMENT: frozenset(
        {KYCStatus.EDD_REQUIRED, KYCStatus.APPROVED, KYCStatus.REJECTED}
    ),
    KYCStatus.EDD_REQUIRED: frozenset({KYCStatus.MLRO_REVIEW, KYCStatus.REJECTED}),
    KYCStatus.MLRO_REVIEW: frozenset({KYCStatus.APPROVED, KYCStatus.REJECTED}),
    KYCStatus.APPROVED: frozenset(),
    KYCStatus.REJECTED: frozenset(),
    KYCStatus.EXPIRED: frozenset(),
}

_STATUS_TO_EVENT: dict[KYCStatus, _SumSubEventType] = {
    KYCStatus.DOCUMENT_REVIEW: "DOCUMENTS_SUBMITTED",
    KYCStatus.RISK_ASSESSMENT: "RISK_ASSESSED",
    KYCStatus.EDD_REQUIRED: "EDD_TRIGGERED",
    KYCStatus.MLRO_REVIEW: "MLRO_REVIEW_STARTED",
    KYCStatus.APPROVED: "APPROVED",
    KYCStatus.REJECTED: "REJECTED",
    KYCStatus.EXPIRED: "EXPIRED",
}


# ── Domain models ─────────────────────────────────────────────────────────────


class SumSubWorkflowRecord(BaseModel, frozen=True):
    """Internal domain record — shadows applicant + SumsubConfigEntity (TypeORM DROP)."""

    workflow_id: str
    applicant_id: str
    customer_id: str
    kyc_type: KYCType
    first_name: str
    last_name: str
    date_of_birth: str
    nationality: str
    country_of_residence: str
    expected_transaction_volume: Decimal
    is_pep: bool
    business_name: str | None
    registration_number: str | None
    status: KYCStatus
    document_ids: tuple[str, ...]
    edd_required: bool
    rejection_reason: RejectionReason | None
    risk_score: int | None
    notes: tuple[str, ...]
    mlro_sign_off: bool
    mlro_user_id: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    model_config = {"arbitrary_types_allowed": True}


class SumSubAuditRecord(BaseModel, frozen=True):
    """Append-only audit event — I-24 compliance. Never folded into KYCWorkflowResult."""

    workflow_id: str
    customer_id: str
    event_type: _SumSubEventType
    status_from: KYCStatus | None
    status_to: KYCStatus
    occurred_at: datetime

    model_config = {"arbitrary_types_allowed": True}


# ── Error ─────────────────────────────────────────────────────────────────────


class SumSubApplicationError(BanxeLegacyAdapterError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _edd_required(request: KYCWorkflowRequest) -> bool:
    if request.is_pep:
        return True
    threshold = (
        _EDD_INDIVIDUAL_THRESHOLD
        if request.kyc_type == KYCType.INDIVIDUAL
        else _EDD_CORPORATE_THRESHOLD
    )
    return request.expected_transaction_volume >= threshold


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacySumSubAdapter:
    """
    KYCWorkflowPort implementation — SumSub individual + corporate KYC (REWRITE-4).

    Idempotency keyed by customer_id — one active workflow per customer.
    In-memory; not durable or concurrency-safe. Production: SumSub REST API Wave E.
    """

    def __init__(self) -> None:
        self._by_workflow_id: dict[str, SumSubWorkflowRecord] = {}
        self._by_customer_id: dict[str, SumSubWorkflowRecord] = {}
        self._audit_log: list[SumSubAuditRecord] = []

    # ── KYCWorkflowPort ───────────────────────────────────────────────────────

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """createApplicant() semantic — I-02/I-04 checks, store PENDING, idempotent."""
        for country_field in (request.nationality, request.country_of_residence):
            if country_field.upper() in _BLOCKED_COUNTRIES:
                raise SumSubApplicationError(
                    f"Blocked jurisdiction: {country_field!r} (I-02)",
                    code="blocked_jurisdiction",
                )

        if request.customer_id in self._by_customer_id:
            return self._to_result(self._by_customer_id[request.customer_id])

        now = datetime.now(UTC)
        record = SumSubWorkflowRecord(
            workflow_id=f"ssub-{secrets.token_hex(8)}",
            applicant_id=f"applicant-{secrets.token_hex(6)}",
            customer_id=request.customer_id,
            kyc_type=request.kyc_type,
            first_name=request.first_name,
            last_name=request.last_name,
            date_of_birth=request.date_of_birth,
            nationality=request.nationality.upper(),
            country_of_residence=request.country_of_residence.upper(),
            expected_transaction_volume=request.expected_transaction_volume,
            is_pep=request.is_pep,
            business_name=request.business_name,
            registration_number=request.registration_number,
            status=KYCStatus.PENDING,
            document_ids=(),
            edd_required=_edd_required(request),
            rejection_reason=None,
            risk_score=None,
            notes=(),
            mlro_sign_off=False,
            mlro_user_id=None,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=_WORKFLOW_TTL_DAYS),
        )
        self._store(record)
        self._emit_audit(record, event_type="CREATED", status_from=None)
        return self._to_result(record)

    def get_workflow(self, workflow_id: str) -> KYCWorkflowResult | None:
        record = self._by_workflow_id.get(workflow_id)
        return self._to_result(record) if record is not None else None

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        """submitUserDocuments() semantic — PENDING → DOCUMENT_REVIEW."""
        record = self._require(workflow_id)
        if record.status != KYCStatus.PENDING:
            raise SumSubApplicationError(
                f"submit_documents requires PENDING, got {record.status}",
                code="invalid_status_for_submit",
            )
        updated = record.model_copy(
            update={
                "status": KYCStatus.DOCUMENT_REVIEW,
                "document_ids": (*record.document_ids, *document_ids),
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(updated)
        self._emit_audit(updated, event_type="DOCUMENTS_SUBMITTED", status_from=record.status)
        return self._to_result(updated)

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """MLRO sign-off — MLRO_REVIEW → APPROVED (I-27 HITL gate)."""
        record = self._require(workflow_id)
        if record.status != KYCStatus.MLRO_REVIEW:
            raise SumSubApplicationError(
                f"approve_edd requires MLRO_REVIEW, got {record.status}",
                code="invalid_status_for_approve_edd",
            )
        updated = record.model_copy(
            update={
                "status": KYCStatus.APPROVED,
                "mlro_sign_off": True,
                "mlro_user_id": mlro_user_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(updated)
        self._emit_audit(updated, event_type="APPROVED", status_from=record.status)
        return self._to_result(updated)

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        """declineApplicant() semantic — any non-terminal → REJECTED."""
        record = self._require(workflow_id)
        if record.status in (KYCStatus.APPROVED, KYCStatus.REJECTED, KYCStatus.EXPIRED):
            raise SumSubApplicationError(
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
        self._emit_audit(updated, event_type="REJECTED", status_from=record.status)
        return self._to_result(updated)

    def health(self) -> bool:
        return True

    # ── Extra (beyond port) ───────────────────────────────────────────────────

    def advance_to(
        self,
        workflow_id: str,
        new_status: KYCStatus,
        *,
        risk_score: int | None = None,
        note: str | None = None,
    ) -> SumSubWorkflowRecord:
        """applicantReviewed() webhook semantic — drive state machine forward."""
        record = self._require(workflow_id)
        if new_status not in _VALID_TRANSITIONS[record.status]:
            raise SumSubApplicationError(
                f"Illegal transition: {record.status} → {new_status}",
                code="invalid_state_transition",
            )
        update: dict[str, object] = {
            "status": new_status,
            "updated_at": datetime.now(UTC),
        }
        if risk_score is not None:
            update["risk_score"] = risk_score
        if note is not None:
            update["notes"] = (*record.notes, note)
        updated = record.model_copy(update=update)
        self._store(updated)
        event: _SumSubEventType = _STATUS_TO_EVENT.get(new_status, "RISK_ASSESSED")
        self._emit_audit(updated, event_type=event, status_from=record.status)
        return updated

    def collect_audit_records(self) -> list[SumSubAuditRecord]:
        """I-24 append-only audit trail."""
        return list(self._audit_log)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _require(self, workflow_id: str) -> SumSubWorkflowRecord:
        record = self._by_workflow_id.get(workflow_id)
        if record is None:
            raise SumSubApplicationError(
                f"Workflow not found: {workflow_id!r}", code="workflow_not_found"
            )
        return record

    def _store(self, record: SumSubWorkflowRecord) -> None:
        self._by_workflow_id[record.workflow_id] = record
        self._by_customer_id[record.customer_id] = record

    def _emit_audit(
        self,
        record: SumSubWorkflowRecord,
        *,
        event_type: _SumSubEventType,
        status_from: KYCStatus | None,
    ) -> None:
        self._audit_log.append(
            SumSubAuditRecord(
                workflow_id=record.workflow_id,
                customer_id=record.customer_id,
                event_type=event_type,
                status_from=status_from,
                status_to=record.status,
                occurred_at=datetime.now(UTC),
            )
        )

    def _to_result(self, record: SumSubWorkflowRecord) -> KYCWorkflowResult:
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
            mlro_sign_off=record.mlro_sign_off,
        )
