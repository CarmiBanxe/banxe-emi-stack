"""
services/aml/sar_service.py — Suspicious Activity Report (SAR) Service
IL-052 | Phase 3 #12 | POCA 2002 s.330 | banxe-emi-stack

WHY THIS EXISTS
---------------
POCA 2002 s.330 requires authorised officers to file a Suspicious Activity
Report (SAR) with the NCA (National Crime Agency) whenever they know or
suspect that a person is engaged in money laundering. Failure to file is a
criminal offence (max 5 years imprisonment).

FCA SYSC 6.3.9R: firms must have a nominated MLRO who reviews SAR decisions.
JMLSG guidance: SARs should be filed promptly — ideally within 24 hours of
the suspicion arising (4h SLA in Banxe system, enforced via HITL SAR_REQUIRED).

SAR LIFECYCLE:
  DRAFT → MLRO_APPROVED → SUBMITTED (NCA SAROnline)
       ↘ WITHDRAWN (MLRO concludes not suspicious)

MLRO GATE (mandatory — cannot be bypassed):
  - Only MLRO-role users can approve or withdraw a SAR
  - SARs cannot be submitted without MLRO_APPROVED status
  - All decisions logged for FCA audit (5-year retention — MLR 2017)

NCA SAROnline:
  STATUS: STUB — requires NCA account + SAROnline API credentials.
  When credentials arrive:
    1. Set NCA_SAR_API_KEY + NCA_ORGANISATION_ID in .env
    2. Replace StubNCAClient with LiveNCAClient in get_sar_service()

Retention: all SAR records retained 5 years in ClickHouse (MLR 2017 Reg.40).
In sandbox: in-memory store only.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)


# ── Enumerations ───────────────────────────────────────────────────────────────


class SARStatus(str, Enum):
    DRAFT = "DRAFT"  # Created, awaiting MLRO review
    MLRO_APPROVED = "MLRO_APPROVED"  # MLRO approved — ready to submit
    SUBMITTED = "SUBMITTED"  # Submitted to NCA SAROnline
    SUBMISSION_FAILED = "SUBMISSION_FAILED"  # Submission attempt failed — retry
    WITHDRAWN = "WITHDRAWN"  # MLRO concluded not suspicious


class SARReason(str, Enum):
    """Grounds for SAR filing (POCA 2002 s.330 + JMLSG guidance)."""

    VELOCITY_BREACH = "VELOCITY_BREACH"  # Unusual transaction volume
    STRUCTURING = "STRUCTURING"  # Sub-threshold splitting (POCA s.330)
    HIGH_RISK_JURISDICTION = "HIGH_RISK_JURISDICTION"  # FATF/UK greylist
    UNUSUAL_PATTERN = "UNUSUAL_PATTERN"  # Activity inconsistent with profile
    PEP_UNEXPLAINED_WEALTH = "PEP_UNEXPLAINED_WEALTH"
    SOURCE_OF_FUNDS_UNKNOWN = "SOURCE_OF_FUNDS_UNKNOWN"
    THRESHOLD_BREACH = "THRESHOLD_BREACH"  # Single tx ≥ auto-SAR threshold
    CONNECTED_ACCOUNTS = "CONNECTED_ACCOUNTS"  # Network / mule account signal
    OTHER = "OTHER"  # MLRO discretion


# ── Domain types ───────────────────────────────────────────────────────────────


@dataclass
class SARReport:
    """
    One Suspicious Activity Report.

    GDPR: SAR records are law-enforcement data — special-category processing
    under GDPR Art.9(2)(g) (public interest). Access must be restricted to
    MLRO and compliance roles. Never returned in customer-facing API responses.
    """

    sar_id: str
    transaction_id: str
    customer_id: str
    entity_type: str
    amount: Decimal
    currency: str
    sar_reasons: list[SARReason]
    aml_flags: list[str]  # From TxMonitorService.evaluate()
    fraud_score: int
    status: SARStatus
    created_at: datetime
    created_by: str  # "system" or operator_id

    # MLRO gate fields
    mlro_reviewed_by: str | None = None
    mlro_reviewed_at: datetime | None = None
    mlro_notes: str = ""

    # Submission fields
    submitted_at: datetime | None = None
    nca_reference: str | None = None  # NCA SAROnline reference number
    errors: list[str] = field(default_factory=list)

    @property
    def is_submittable(self) -> bool:
        """True if MLRO has approved and SAR has not yet been submitted."""
        return self.status == SARStatus.MLRO_APPROVED

    @property
    def requires_mlro_action(self) -> bool:
        return self.status == SARStatus.DRAFT


@dataclass
class SARStats:
    """Aggregated SAR metrics for MLRO dashboard / FCA reporting."""

    total: int
    draft: int
    mlro_approved: int
    submitted: int
    submission_failed: int
    withdrawn: int
    submission_rate: float  # submitted / (submitted + withdrawn) * 100


# ── NCA Client (stub) ─────────────────────────────────────────────────────────


class StubNCAClient:
    """
    Stub NCA SAROnline client.
    Returns a deterministic reference. Does NOT send to NCA.
    Replace with LiveNCAClient when NCA credentials are provisioned.
    """

    def submit(self, sar: SARReport) -> str:
        """Returns fake NCA reference: SAR-YYYYMM-{sar_id[:8]}."""
        month = sar.created_at.strftime("%Y%m")
        return f"SAR-{month}-{sar.sar_id[:8].upper()}"


# ── Service ────────────────────────────────────────────────────────────────────


class SARServiceError(Exception):
    """Raised for invalid SAR operations."""


class SARService:
    """
    In-memory SAR management service.
    In production: persist to ClickHouse with 5-year TTL (MLR 2017 Reg.40).
    """

    def __init__(self, nca_client: StubNCAClient | None = None) -> None:
        self._sars: dict[str, SARReport] = {}
        self._nca = nca_client or StubNCAClient()

    # ── File (create draft) ───────────────────────────────────────────────────

    def file_sar(
        self,
        transaction_id: str,
        customer_id: str,
        entity_type: str,
        amount: Decimal,
        currency: str,
        sar_reasons: list[SARReason],
        aml_flags: list[str],
        fraud_score: int,
        created_by: str = "system",
    ) -> SARReport:
        """
        Create a DRAFT SAR awaiting MLRO review.
        Called automatically when TxMonitorService sets aml_sar_required=True
        and the HITL case is escalated.
        """
        sar = SARReport(
            sar_id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            customer_id=customer_id,
            entity_type=entity_type,
            amount=amount,
            currency=currency,
            sar_reasons=list(sar_reasons),
            aml_flags=list(aml_flags),
            fraud_score=fraud_score,
            status=SARStatus.DRAFT,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )
        self._sars[sar.sar_id] = sar
        logger.warning(
            "SAR DRAFT created: sar=%s tx=%s customer=%s amount=£%s reasons=%s",
            sar.sar_id,
            transaction_id,
            customer_id,
            amount,
            [r.value for r in sar_reasons],
        )
        return sar

    # ── MLRO gate ─────────────────────────────────────────────────────────────

    def approve_sar(
        self,
        sar_id: str,
        mlro_id: str,
        notes: str = "",
    ) -> SARReport:
        """
        MLRO approves SAR for submission to NCA.
        POCA 2002 s.330: MLRO must have reasonable grounds to suspect ML.
        """
        sar = self._get_or_raise(sar_id)
        if sar.status != SARStatus.DRAFT:
            raise SARServiceError(
                f"SAR {sar_id} is {sar.status.value} — can only approve DRAFT SARs"
            )
        sar.status = SARStatus.MLRO_APPROVED
        sar.mlro_reviewed_by = mlro_id
        sar.mlro_reviewed_at = datetime.now(UTC)
        sar.mlro_notes = notes
        logger.warning("SAR MLRO_APPROVED: sar=%s by=%s", sar_id, mlro_id)
        return sar

    def withdraw_sar(
        self,
        sar_id: str,
        mlro_id: str,
        reason: str,
    ) -> SARReport:
        """
        MLRO withdraws SAR — concluded not suspicious after review.
        Withdrawal reason must be documented (JMLSG guidance §6.7).
        """
        sar = self._get_or_raise(sar_id)
        if sar.status not in (SARStatus.DRAFT, SARStatus.MLRO_APPROVED):
            raise SARServiceError(f"SAR {sar_id} is {sar.status.value} — cannot withdraw")
        sar.status = SARStatus.WITHDRAWN
        sar.mlro_reviewed_by = mlro_id
        sar.mlro_reviewed_at = datetime.now(UTC)
        sar.mlro_notes = reason
        logger.info("SAR WITHDRAWN: sar=%s by=%s reason=%s", sar_id, mlro_id, reason)
        return sar

    # ── Submission ────────────────────────────────────────────────────────────

    def submit_sar(self, sar_id: str) -> SARReport:
        """
        Submit MLRO-approved SAR to NCA SAROnline.
        Cannot submit without prior MLRO approval.
        """
        sar = self._get_or_raise(sar_id)
        if not sar.is_submittable:
            raise SARServiceError(
                f"SAR {sar_id} is {sar.status.value} — must be MLRO_APPROVED to submit"
            )
        try:
            nca_ref = self._nca.submit(sar)
            sar.status = SARStatus.SUBMITTED
            sar.submitted_at = datetime.now(UTC)
            sar.nca_reference = nca_ref
            logger.warning("SAR SUBMITTED to NCA: sar=%s nca_ref=%s", sar_id, nca_ref)
        except Exception as exc:
            sar.status = SARStatus.SUBMISSION_FAILED
            sar.errors.append(f"NCA submission failed: {exc}")
            logger.error("SAR submission failed: sar=%s exc=%s", sar_id, exc)
        return sar

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_sar(self, sar_id: str) -> SARReport | None:
        return self._sars.get(sar_id)

    def list_sars(self, status: SARStatus | None = None) -> list[SARReport]:
        """List SARs, optionally filtered by status. Sorted newest-first."""
        sars = list(self._sars.values())
        if status is not None:
            sars = [s for s in sars if s.status == status]
        return sorted(sars, key=lambda s: s.created_at, reverse=True)

    def stats(self) -> SARStats:
        sars = list(self._sars.values())
        by_status = {s: 0 for s in SARStatus}
        for s in sars:
            by_status[s.status] += 1
        submitted = by_status[SARStatus.SUBMITTED]
        withdrawn = by_status[SARStatus.WITHDRAWN]
        rate = 0.0
        if submitted + withdrawn > 0:
            rate = round(submitted / (submitted + withdrawn) * 100, 1)
        return SARStats(
            total=len(sars),
            draft=by_status[SARStatus.DRAFT],
            mlro_approved=by_status[SARStatus.MLRO_APPROVED],
            submitted=submitted,
            submission_failed=by_status[SARStatus.SUBMISSION_FAILED],
            withdrawn=withdrawn,
            submission_rate=rate,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_or_raise(self, sar_id: str) -> SARReport:
        sar = self._sars.get(sar_id)
        if sar is None:
            raise SARServiceError(f"SAR {sar_id} not found")
        return sar
