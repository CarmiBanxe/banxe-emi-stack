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
  Two clients implement the same async ``NCAClient`` seam:
    - StubNCAClient  — offline/deterministic; the default with NO credentials.
    - LiveNCAClient  — real httpx POST to NCA SAROnline (sandbox by default).
  CUTOVER (stub → live) is automatic in ``_get_sar_service()`` (api/routers/
  reporting.py): LiveNCAClient is selected IFF both NCA_SAR_API_KEY and
  NCA_ORGANISATION_ID are present in the environment; otherwise StubNCAClient,
  so dev/test/CI without credentials keep working offline.
  ENV (LiveNCAClient):
    - NCA_SAR_BASE_URL    — SAROnline base URL; DEFAULTS to the TEST/sandbox
                            endpoint so S6 acceptance (a) runs against the NCA
                            test env, not production. Operator overrides for prod.
    - NCA_SAR_API_KEY     — SAROnline API key (bearer).
    - NCA_ORGANISATION_ID — NCA-assigned organisation id.
  PII: a SAR is a suspicious-activity report — its body is PII BY LAWFUL PURPOSE
  (POCA 2002 s.330). That body is sent ONLY to NCA. Decision-lineage
  (AgentDecisionRecord, ADR-046) carries ONLY the SAR id + status +
  nca_reference — never the report body (see ``_emit_submission_lineage``).

Retention: all SAR records retained 5 years in ClickHouse (MLR 2017 Reg.40).
In sandbox: in-memory store only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import logging
import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable
import uuid

import httpx

if TYPE_CHECKING:
    from services.agents._lineage import DecisionRecorder

# ─── BANXE COMPLIANCE RAG (auto-injected) ───
try:
    import sys as _sys

    _sys.path.insert(0, "/data/compliance")
    from compliance_agent_client import rag_context as _rag_context

    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

    def _rag_context(agent, query, k=3):
        return ""


def get_compliance_context(query, agent_name=None, k=3):
    """Получить compliance-контекст из базы знаний для промпта."""
    if not _RAG_AVAILABLE:
        return ""
    return _rag_context(agent_name or "banxe_aml_sar_agent", query, k)


# ─────────────────────────────────────────────


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


# ── NCA Client seam ───────────────────────────────────────────────────────────


class SARSubmissionError(Exception):
    """
    Raised when an NCA SAROnline submission fails (non-2xx, transport, or
    timeout). NEVER swallowed silently — surfaces the upstream failure to the
    caller so the SAR is not falsely recorded as SUBMITTED.

    ``status_code`` is the NCA HTTP status when the failure was an HTTP response
    (None for transport/timeout failures).
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@runtime_checkable
class NCAClient(Protocol):
    """Async submission seam — both Stub and Live clients satisfy it."""

    async def submit(self, sar: SARReport) -> str:
        """Submit ``sar`` to NCA SAROnline and return the NCA reference."""
        ...


# ── NCA test/sandbox default ────────────────────────────────────────────────
# Default base URL points at the SAROnline TEST/sandbox env so S6 acceptance (a)
# can never hit production by accident. The operator overrides NCA_SAR_BASE_URL
# with the NCA-provided sandbox/prod URL at runtime.
_NCA_SAR_TEST_BASE_URL = "https://test.saronline.nca.gov.uk"
_NCA_SUBMIT_PATH = "/v1/sar/submit"
# Response keys NCA SAROnline may use for the assigned reference (tolerant parse).
_NCA_REFERENCE_KEYS = (
    "nca_reference",
    "ncaReference",
    "reference",
    "sarReference",
    "submissionReference",
    "reference_number",
)


class StubNCAClient:
    """
    Stub NCA SAROnline client (offline fallback — DO NOT remove).
    Returns a deterministic reference. Does NOT send to NCA. Used whenever NCA
    credentials are absent (dev/test/CI). Async to match the NCAClient seam.
    """

    async def submit(self, sar: SARReport) -> str:
        """Returns fake NCA reference: SAR-YYYYMM-{sar_id[:8]}."""
        month = sar.created_at.strftime("%Y%m")
        return f"SAR-{month}-{sar.sar_id[:8].upper()}"


class LiveNCAClient:
    """
    Live NCA SAROnline client — real async HTTP submission via httpx.

    AWAIT DISCIPLINE (adapter bug class): every network call is ``await``ed.
    A missing ``await`` would yield a coroutine instead of a Response and fail
    loudly in tests (strict MockTransport/AsyncMock), never silently no-op.

    Idempotency: the SAR id is sent as an ``Idempotency-Key`` so a transient
    retry (timeout/5xx) cannot create a duplicate filing at NCA. Combined with
    the service-level submission lock (already-SUBMITTED → no-op), submission is
    safe to retry.

    Credentials/endpoint come from the environment (NCA_SAR_BASE_URL defaults to
    the TEST/sandbox URL). The httpx client is injectable for tests.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        organisation_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._base_url = (
            base_url or os.environ.get("NCA_SAR_BASE_URL", _NCA_SAR_TEST_BASE_URL)
        ).rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get("NCA_SAR_API_KEY", "")
        self._org_id = (
            organisation_id
            if organisation_id is not None
            else os.environ.get("NCA_ORGANISATION_ID", "")
        )
        if not self._api_key or not self._org_id:
            raise OSError(
                "NCA_SAR_API_KEY and NCA_ORGANISATION_ID must be set to use "
                "LiveNCAClient. Leave them unset to fall back to StubNCAClient "
                "(offline) — see _get_sar_service()."
            )
        self._client = client if client is not None else httpx.AsyncClient()
        self._owns_client = client is None
        self._timeout_s = timeout_s
        self._max_retries = max(0, max_retries)

    async def submit(self, sar: SARReport) -> str:
        """
        POST the SAR to NCA SAROnline and return the assigned NCA reference.

        2xx                  → parse + return the NCA reference
        4xx                  → SARSubmissionError (client error — NOT retried)
        5xx / transport / timeout → retried up to ``max_retries``; on exhaustion,
                               SARSubmissionError (no silent swallow).
        """
        url = f"{self._base_url}{_NCA_SUBMIT_PATH}"
        payload = self._build_payload(sar)  # PII by lawful purpose — NCA only.
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Organisation-Id": self._org_id,
            "Idempotency-Key": sar.sar_id,  # submission lock — safe retry
        }
        last_error: SARSubmissionError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    url, json=payload, headers=headers, timeout=self._timeout_s
                )
            except httpx.HTTPError as exc:
                last_error = SARSubmissionError(
                    f"NCA SAROnline transport error: {type(exc).__name__}: {exc}"
                )
                continue  # transient — retry
            if 200 <= response.status_code < 300:
                return self._parse_reference(response)
            if response.status_code >= 500:
                last_error = SARSubmissionError(
                    f"NCA SAROnline server error: HTTP {response.status_code}",
                    status_code=response.status_code,
                )
                continue  # transient — retry
            # 4xx — client error; the request itself is wrong, retry won't help.
            raise SARSubmissionError(
                f"NCA SAROnline rejected SAR {sar.sar_id}: HTTP {response.status_code} "
                f"{self._safe_snippet(response)}",
                status_code=response.status_code,
            )
        raise last_error or SARSubmissionError(
            f"NCA SAROnline submission failed for SAR {sar.sar_id}"
        )

    def _build_payload(self, sar: SARReport) -> dict[str, object]:
        """Map a SARReport to the NCA SAROnline submission body.

        Money is serialised via ``str(Decimal)`` — never float."""
        return {
            "organisationId": self._org_id,
            "sarId": sar.sar_id,
            "transactionId": sar.transaction_id,
            "subject": {"customerId": sar.customer_id, "entityType": sar.entity_type},
            "amount": str(sar.amount),
            "currency": sar.currency,
            "reasons": [r.value for r in sar.sar_reasons],
            "amlFlags": list(sar.aml_flags),
            "fraudScore": sar.fraud_score,
            "createdAt": sar.created_at.isoformat(),
        }

    @staticmethod
    def _parse_reference(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError as exc:
            raise SARSubmissionError(
                f"NCA SAROnline returned non-JSON 2xx body: {exc}",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, dict):
            for key in _NCA_REFERENCE_KEYS:
                value = data.get(key)
                if value:
                    return str(value)
        raise SARSubmissionError(
            "NCA SAROnline accepted the SAR (2xx) but returned no reference",
            status_code=response.status_code,
        )

    @staticmethod
    def _safe_snippet(response: httpx.Response) -> str:
        """A short, bounded slice of the NCA error body for diagnostics.

        httpx decodes with errors='replace', so ``.text`` does not raise."""
        return response.text[:200]

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


# ── Service ────────────────────────────────────────────────────────────────────


class SARServiceError(Exception):
    """Raised for invalid SAR operations."""


class SARService:
    """
    In-memory SAR management service.
    In production: persist to ClickHouse with 5-year TTL (MLR 2017 Reg.40).
    """

    def __init__(
        self,
        nca_client: NCAClient | None = None,
        decision_recorder: DecisionRecorder | None = None,
    ) -> None:
        self._sars: dict[str, SARReport] = {}
        self._nca: NCAClient = nca_client or StubNCAClient()
        # Optional ADR-046 lineage sink. OFF by default → behaviour unchanged for
        # existing callers/tests. When injected, a SUBMITTED SAR emits one
        # decision record carrying ONLY id+status+nca_reference (never the body).
        self._recorder = decision_recorder

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

    async def submit_sar(self, sar_id: str) -> SARReport:
        """
        Submit an MLRO-approved SAR to NCA SAROnline (async — awaits the client).

        Guard rails (preserve the state machine, POCA 2002 s.330):
          - Submission lock / idempotency: an already-SUBMITTED SAR that has an
            nca_reference is a NO-OP — never submitted twice.
          - MLRO gate: only MLRO_APPROVED (or a prior SUBMISSION_FAILED retry)
            SARs may submit; anything else raises SARServiceError.
          - On NCA failure: status → SUBMISSION_FAILED, the error is recorded,
            and SARSubmissionError is re-raised (no silent swallow).
        """
        sar = self._get_or_raise(sar_id)

        # Idempotent submission lock — already filed → no-op (safe on retry).
        if sar.status == SARStatus.SUBMITTED and sar.nca_reference:
            logger.info(
                "SAR already SUBMITTED — idempotent no-op: sar=%s nca_ref=%s",
                sar_id,
                sar.nca_reference,
            )
            return sar

        # MLRO gate. MLRO_APPROVED is the entry state; SUBMISSION_FAILED is a
        # retry of a previously-approved SAR (still gated — never bypasses MLRO).
        if sar.status not in (SARStatus.MLRO_APPROVED, SARStatus.SUBMISSION_FAILED):
            raise SARServiceError(
                f"SAR {sar_id} is {sar.status.value} — must be MLRO_APPROVED to submit"
            )

        try:
            nca_ref = await self._nca.submit(sar)
        except SARSubmissionError as exc:
            sar.status = SARStatus.SUBMISSION_FAILED
            sar.errors.append(f"NCA submission failed: {exc}")
            logger.error("SAR submission failed: sar=%s exc=%s", sar_id, exc)
            raise

        sar.status = SARStatus.SUBMITTED
        sar.submitted_at = datetime.now(UTC)
        sar.nca_reference = nca_ref
        logger.warning("SAR SUBMITTED to NCA: sar=%s nca_ref=%s", sar_id, nca_ref)
        await self._emit_submission_lineage(sar)
        return sar

    async def _emit_submission_lineage(self, sar: SARReport) -> None:
        """Emit one ADR-046 decision record for a submitted SAR.

        R-SEC: the record carries ONLY the SAR id, status, and nca_reference plus
        the MLRO reviewer id (operator, not subject PII). The SAR body — customer
        id, transaction id, amount, reasons, flags — is NEVER placed on the
        lineage record (it lives solely in the NCA payload). No-op if no recorder
        is wired.
        """
        if self._recorder is None:
            return
        # Local import: keeps module load light and avoids pulling the agents
        # package unless lineage recording is actually enabled.
        from services.agents._lineage import AgentDecisionRecord, ComplianceResult

        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            agent_id="banxe_aml_sar_agent",
            triggering_event=f"sar_submit:{sar.sar_id}",
            intent="sar.submit",
            policies_evaluated=["POCA-2002-s330", "MLR-2017-Reg40"],
            compliance_result=ComplianceResult.PASS,
            reasoning_summary=f"SAR submitted to NCA SAROnline (status={sar.status.value})",
            confidence_score=1.0,
            action_taken=f"NCA_SUBMITTED nca_reference={sar.nca_reference}",
            human_reviewed_by=sar.mlro_reviewed_by,
            correlation_id=sar.sar_id,
        )
        await self._recorder.record(record)

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
