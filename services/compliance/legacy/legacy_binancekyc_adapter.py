"""
legacy_binancekyc_adapter.py — LegacyBinanceKYCAdapter implements KYCWorkflowPort (REWRITE-6).

Semantic rewrite of binance-kyc-connector.service.ts (banxe-identity) — crypto-native
tiered KYC workflow.
Transport dropped per ADR-025 §15-16:
  - BinanceApiClient (HMAC-signed axios HTTP, /sapi/v1/kyc/*)
  - TypeORM (BinanceKYCEntity, BinanceVerificationTierEntity)
  - RabbitMQ publishers (REQUEST_BINANCE_KYC_CREATE, KYC_TIER_UPGRADED)
  - NestJS DI / @Injectable / @InjectRepository
  - ConfigService (BINANCE_API_KEY, BINANCE_SECRET_KEY)

Binance provider tier → KYCWorkflowPort mapping:
  initiateTier1(dto)            → create_workflow(request)          PENDING
  submitTier2Documents(docs)     → submit_documents(id, docs)        DOCUMENT_REVIEW
  [risk engine callback]         → advance_to(id, RISK_ASSESSMENT)   RISK_ASSESSMENT
  [EDD trigger]                  → advance_to(id, EDD_REQUIRED)      EDD_REQUIRED
  [MLRO pickup]                  → advance_to(id, MLRO_REVIEW)       MLRO_REVIEW
  approveTier3(id, mlro_id)      → approve_edd(id, mlro_id)          APPROVED
  rejectApplicant(id, reason)    → reject_workflow(id, reason)        REJECTED

Provider tier normalisation (deterministic, no I/O):
  TIER_1_BASIC         → KYCStatus.PENDING
  TIER_2_INTERMEDIATE  → KYCStatus.DOCUMENT_REVIEW
  TIER_3_FULL          → KYCStatus.RISK_ASSESSMENT

State machine (mirrors SumSub — shared FCA path):
  PENDING          → DOCUMENT_REVIEW | REJECTED | EXPIRED
  DOCUMENT_REVIEW  → RISK_ASSESSMENT | REJECTED | EXPIRED
  RISK_ASSESSMENT  → EDD_REQUIRED    | APPROVED  | REJECTED
  EDD_REQUIRED     → MLRO_REVIEW     | REJECTED
  MLRO_REVIEW      → APPROVED        | REJECTED
  APPROVED / REJECTED / EXPIRED → (terminal)

I-02: RU/BY/IR/KP/CU/MM/AF/VE/SY blocked at create_workflow on nationality +
      country_of_residence.
I-04 (INDIVIDUAL/SOLE_TRADER): EDD if expected_transaction_volume ≥ £10k OR is_pep=True.
I-04 (BUSINESS): EDD if expected_transaction_volume ≥ £50k OR is_pep=True.
I-24: BinanceKYCAuditRecord append-only — never folded into KYCWorkflowResult.
I-27: approve_edd gated on status in {EDD_REQUIRED, MLRO_REVIEW} AND edd_required=True.

Idempotency (same as SumSub): returns existing non-terminal workflow for same customer_id.
Canon: ADR-025 §15-16 + services.kyc.kyc_port + SESSION-2026-05-08-WAVE-D-REWRITE-6
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
from services.shared.errors import BanxeLegacyAdapterError

# ── Constants ─────────────────────────────────────────────────────────────────

_BLOCKED_COUNTRIES: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)
_EDD_INDIVIDUAL_THRESHOLD: Decimal = Decimal("10000.00")  # I-04 individual / sole-trader
_EDD_CORPORATE_THRESHOLD: Decimal = Decimal("50000.00")  # I-04 business
_WORKFLOW_TTL_DAYS: int = 30  # FCA MLR 2017

_BinanceEventType = Literal[
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

_STATUS_TO_EVENT: dict[KYCStatus, _BinanceEventType] = {
    KYCStatus.DOCUMENT_REVIEW: "DOCUMENTS_SUBMITTED",
    KYCStatus.RISK_ASSESSMENT: "RISK_ASSESSED",
    KYCStatus.EDD_REQUIRED: "EDD_TRIGGERED",
    KYCStatus.MLRO_REVIEW: "MLRO_REVIEW_STARTED",
    KYCStatus.APPROVED: "APPROVED",
    KYCStatus.REJECTED: "REJECTED",
    KYCStatus.EXPIRED: "EXPIRED",
}

# ── Provider tier enum & normalisation ────────────────────────────────────────


class BinanceKYCTier(str, Enum):
    """Binance-side verification tiers — provider-specific, not exposed via port."""

    TIER_1_BASIC = "TIER_1_BASIC"  # email + phone verified
    TIER_2_INTERMEDIATE = "TIER_2_INTERMEDIATE"  # government ID document
    TIER_3_FULL = "TIER_3_FULL"  # address proof + video selfie


_TIER_STATUS_MAP: dict[BinanceKYCTier, KYCStatus] = {
    BinanceKYCTier.TIER_1_BASIC: KYCStatus.PENDING,
    BinanceKYCTier.TIER_2_INTERMEDIATE: KYCStatus.DOCUMENT_REVIEW,
    BinanceKYCTier.TIER_3_FULL: KYCStatus.RISK_ASSESSMENT,
}


def normalize_binance_tier(tier: BinanceKYCTier) -> KYCStatus:
    """Maps Binance provider tier to canonical KYCStatus. Pure, no I/O."""
    return _TIER_STATUS_MAP[tier]


# ── Domain models ─────────────────────────────────────────────────────────────


class BinanceVerificationRecord(BaseModel, frozen=True):
    """Internal domain record — shadows BinanceKYCEntity (TypeORM DROP)."""

    workflow_id: str
    verification_id: str  # Binance-side applicant identifier
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
    current_tier: BinanceKYCTier
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


class BinanceKYCAuditRecord(BaseModel, frozen=True):
    """Append-only audit event — I-24 compliance. Never folded into KYCWorkflowResult."""

    workflow_id: str
    customer_id: str
    event_type: _BinanceEventType
    status_from: KYCStatus | None
    status_to: KYCStatus
    occurred_at: datetime

    model_config = {"arbitrary_types_allowed": True}


# ── Error ─────────────────────────────────────────────────────────────────────


class BinanceKYCError(BanxeLegacyAdapterError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


# ── EDD helper ────────────────────────────────────────────────────────────────


def _compute_edd(request: KYCWorkflowRequest) -> bool:
    if request.is_pep:
        return True
    threshold = (
        _EDD_INDIVIDUAL_THRESHOLD
        if request.kyc_type != KYCType.BUSINESS
        else _EDD_CORPORATE_THRESHOLD
    )
    return request.expected_transaction_volume >= threshold


# ── Adapter ───────────────────────────────────────────────────────────────────


class LegacyBinanceKYCAdapter:
    """
    KYCWorkflowPort implementation — Binance tiered KYC (REWRITE-6).

    Tiered provider model (TIER_1→TIER_2→TIER_3) normalised to canonical KYCStatus
    via normalize_binance_tier(). Idempotency: returns existing non-terminal workflow
    for same customer_id (same behaviour as SumSub adapter).
    In-memory; not durable or concurrency-safe. Production: Binance REST /sapi/v1/kyc/*.
    """

    def __init__(self) -> None:
        self._by_workflow_id: dict[str, BinanceVerificationRecord] = {}
        self._by_customer_id: dict[str, BinanceVerificationRecord] = {}
        self._audit_log: list[BinanceKYCAuditRecord] = []

    # ── KYCWorkflowPort ───────────────────────────────────────────────────────

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """initiateTier1() semantic — I-02/I-04 checks, store PENDING, idempotent."""
        for field_val in (request.nationality, request.country_of_residence):
            if field_val.upper() in _BLOCKED_COUNTRIES:
                raise BinanceKYCError(
                    f"Blocked jurisdiction: {field_val!r} (I-02)",
                    code="blocked_jurisdiction",
                )

        if request.customer_id in self._by_customer_id:
            return self._to_result(self._by_customer_id[request.customer_id])

        now = datetime.now(UTC)
        record = BinanceVerificationRecord(
            workflow_id=f"bnkyc-{secrets.token_hex(8)}",
            verification_id=f"verify-{secrets.token_hex(6)}",
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
            current_tier=BinanceKYCTier.TIER_1_BASIC,
            status=KYCStatus.PENDING,
            document_ids=(),
            edd_required=_compute_edd(request),
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
        """submitTier2Documents() semantic — PENDING → DOCUMENT_REVIEW."""
        record = self._require(workflow_id)
        if record.status != KYCStatus.PENDING:
            raise BinanceKYCError(
                f"submit_documents requires PENDING, got {record.status}",
                code="invalid_status_for_submit",
            )
        updated = record.model_copy(
            update={
                "current_tier": BinanceKYCTier.TIER_2_INTERMEDIATE,
                "status": KYCStatus.DOCUMENT_REVIEW,
                "document_ids": (*record.document_ids, *document_ids),
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(updated)
        self._emit_audit(updated, event_type="DOCUMENTS_SUBMITTED", status_from=record.status)
        return self._to_result(updated)

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """approveTier3() semantic — I-27 gate: EDD_REQUIRED|MLRO_REVIEW + edd_required."""
        record = self._require(workflow_id)
        if record.status not in (KYCStatus.EDD_REQUIRED, KYCStatus.MLRO_REVIEW):
            raise BinanceKYCError(
                f"approve_edd requires EDD_REQUIRED or MLRO_REVIEW, got {record.status}",
                code="invalid_status_for_approve",
            )
        if not record.edd_required:
            raise BinanceKYCError(
                "approve_edd called but edd_required=False (I-27)",
                code="edd_not_required",
            )
        updated = record.model_copy(
            update={
                "current_tier": BinanceKYCTier.TIER_3_FULL,
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
        """rejectApplicant() semantic — any non-terminal → REJECTED."""
        record = self._require(workflow_id)
        _TERMINAL = frozenset({KYCStatus.APPROVED, KYCStatus.REJECTED, KYCStatus.EXPIRED})
        if record.status in _TERMINAL:
            raise BinanceKYCError(
                f"Cannot reject terminal workflow (status={record.status})",
                code="already_terminal",
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

    # ── Extra: provider state machine ────────────────────────────────────────

    def advance_to(
        self,
        workflow_id: str,
        target_status: KYCStatus,
        *,
        risk_score: int | None = None,
        note: str | None = None,
    ) -> KYCWorkflowResult:
        """Advance workflow through post-TIER_2 states (risk engine / MLRO callbacks)."""
        record = self._require(workflow_id)
        allowed = _VALID_TRANSITIONS.get(record.status, frozenset())
        if target_status not in allowed:
            raise BinanceKYCError(
                f"Invalid transition {record.status} → {target_status}",
                code="invalid_transition",
            )
        now = datetime.now(UTC)
        new_tier = record.current_tier
        if target_status == KYCStatus.RISK_ASSESSMENT:
            new_tier = BinanceKYCTier.TIER_3_FULL
        update: dict = {
            "current_tier": new_tier,
            "status": target_status,
            "updated_at": now,
        }
        if risk_score is not None:
            update["risk_score"] = risk_score
        if note is not None:
            update["notes"] = (*record.notes, note)
        updated = record.model_copy(update=update)
        self._store(updated)
        event: _BinanceEventType = _STATUS_TO_EVENT.get(target_status, "APPROVED")
        self._emit_audit(updated, event_type=event, status_from=record.status)
        return self._to_result(updated)

    def collect_audit_records(self) -> list[BinanceKYCAuditRecord]:
        return list(self._audit_log)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _require(self, workflow_id: str) -> BinanceVerificationRecord:
        record = self._by_workflow_id.get(workflow_id)
        if record is None:
            raise BinanceKYCError(
                f"Workflow not found: {workflow_id!r}",
                code="workflow_not_found",
            )
        return record

    def _store(self, record: BinanceVerificationRecord) -> None:
        self._by_workflow_id[record.workflow_id] = record
        self._by_customer_id[record.customer_id] = record

    def _emit_audit(
        self,
        record: BinanceVerificationRecord,
        *,
        event_type: _BinanceEventType,
        status_from: KYCStatus | None,
    ) -> None:
        self._audit_log.append(
            BinanceKYCAuditRecord(
                workflow_id=record.workflow_id,
                customer_id=record.customer_id,
                event_type=event_type,
                status_from=status_from,
                status_to=record.status,
                occurred_at=datetime.now(UTC),
            )
        )

    def _to_result(self, record: BinanceVerificationRecord) -> KYCWorkflowResult:
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
