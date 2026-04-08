"""
mock_kyc_workflow.py — In-memory Mock KYC Workflow Engine (S5-13 / Ballerine)
FCA MLR 2017 | banxe-emi-stack

WHY THIS EXISTS
---------------
Ballerine requires a running instance. MockKYCWorkflow provides a deterministic
in-memory state machine that:
  - Triggers EDD automatically for PEPs, high-risk jurisdictions, large volumes
  - Enforces MLRO sign-off for EDD cases (FCA MLR 2017 §33)
  - Rejects on hard-block jurisdictions (INVARIANTS.md I-02)
  - Expires workflows after 30 days

State machine transitions:
  PENDING → DOCUMENT_REVIEW  (submit_documents called)
  DOCUMENT_REVIEW → RISK_ASSESSMENT  (auto, after document acceptance)
  RISK_ASSESSMENT → EDD_REQUIRED    (if EDD trigger present)
  RISK_ASSESSMENT → APPROVED         (clean, low-risk)
  RISK_ASSESSMENT → REJECTED         (sanctions / high risk)
  EDD_REQUIRED → MLRO_REVIEW         (auto, referral to MLRO)
  MLRO_REVIEW → APPROVED             (mlro approve_edd)
  MLRO_REVIEW → REJECTED             (mlro reject)
  Any → EXPIRED                      (TTL elapsed)
"""
from __future__ import annotations

import logging as _logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowPort,
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)

# FCA MLR 2017: CDD must be completed; 30 days is the standard operational TTL
_WORKFLOW_TTL_DAYS = 30

# INVARIANTS.md I-02 — hard-block jurisdictions
_BLOCKED_COUNTRIES = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE"}

# I-03 — high-risk jurisdictions (FATF greylist) → EDD required
_HIGH_RISK_COUNTRIES = {
    "SY", "IQ", "LB", "YE", "HT", "ML", "DZ", "AO", "BO", "VG",
    "CM", "CI", "CD", "KE", "LA", "MC", "NA", "NP", "SS", "TT",
    "VU", "BG", "VN",
}

# I-04 — EDD threshold
_EDD_VOLUME_THRESHOLD = Decimal("10000")


class MockKYCWorkflow:
    """
    Deterministic in-memory KYC state machine.
    Satisfies KYCWorkflowPort. No external dependencies.
    """

    def __init__(self) -> None:
        self._workflows: dict[str, KYCWorkflowResult] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """Create new KYC workflow and run initial risk check."""
        now = self._now()
        workflow_id = f"kyc-{uuid.uuid4().hex[:12]}"

        result = KYCWorkflowResult(
            workflow_id=workflow_id,
            customer_id=request.customer_id,
            status=KYCStatus.PENDING,
            kyc_type=request.kyc_type,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=_WORKFLOW_TTL_DAYS),
        )

        # Hard-block check (I-02)
        if request.nationality in _BLOCKED_COUNTRIES or \
                request.country_of_residence in _BLOCKED_COUNTRIES:
            result.status = KYCStatus.REJECTED
            result.rejection_reason = RejectionReason.HIGH_RISK_JURISDICTION
            result.risk_score = 100
            result.notes.append(
                f"Blocked jurisdiction detected: nationality={request.nationality} "
                f"residence={request.country_of_residence}"
            )
            self._workflows[workflow_id] = result
            return result

        # EDD triggers (I-03, I-04, MLR 2017 §33)
        edd_triggers = []
        if request.is_pep:
            edd_triggers.append("PEP status")
        if request.nationality in _HIGH_RISK_COUNTRIES or \
                request.country_of_residence in _HIGH_RISK_COUNTRIES:
            edd_triggers.append(
                f"High-risk jurisdiction: {request.nationality or request.country_of_residence}"
            )
        if request.expected_transaction_volume >= _EDD_VOLUME_THRESHOLD:
            edd_triggers.append(
                f"Expected volume £{request.expected_transaction_volume:,.0f} ≥ £10,000 (I-04)"
            )

        result.edd_required = bool(edd_triggers)
        if edd_triggers:
            result.notes.extend(edd_triggers)

        self._workflows[workflow_id] = result
        return result

    def get_workflow(self, workflow_id: str) -> Optional[KYCWorkflowResult]:
        result = self._workflows.get(workflow_id)
        if result is None:
            return None
        # Check TTL
        if not result.is_terminal and self._now() > result.expires_at:
            result.status = KYCStatus.EXPIRED
            result.updated_at = self._now()
        return result

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        """Advance PENDING → DOCUMENT_REVIEW → RISK_ASSESSMENT (→ EDD/APPROVED/REJECTED)."""
        result = self._workflows.get(workflow_id)
        if result is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        if result.is_terminal:
            raise ValueError(f"Workflow {workflow_id} is in terminal state {result.status}")
        if not document_ids:
            raise ValueError("At least one document_id required")

        result.updated_at = self._now()
        result.notes.append(f"Documents submitted: {', '.join(document_ids)}")
        result.status = KYCStatus.DOCUMENT_REVIEW

        # Auto-advance to RISK_ASSESSMENT (mock: instant)
        result.status = KYCStatus.RISK_ASSESSMENT

        # Risk scoring (simplified)
        score = 10  # base
        if result.edd_required:
            score += 40
        result.risk_score = min(score, 100)

        # Terminal decision
        if result.edd_required:
            result.status = KYCStatus.EDD_REQUIRED
            result.status = KYCStatus.MLRO_REVIEW  # auto-refer to MLRO
            result.notes.append("Case referred to MLRO for EDD sign-off (FCA MLR 2017 §33)")
        elif score >= 70:
            result.status = KYCStatus.REJECTED
            result.rejection_reason = RejectionReason.RISK_SCORE_TOO_HIGH
        else:
            result.status = KYCStatus.APPROVED
            result.notes.append("KYC APPROVED — CDD complete (FCA MLR 2017 §18)")

        return result

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """MLRO signs off EDD → APPROVED. Only valid in MLRO_REVIEW state."""
        result = self._workflows.get(workflow_id)
        if result is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        if result.status != KYCStatus.MLRO_REVIEW:
            raise ValueError(
                f"approve_edd only valid in MLRO_REVIEW state, current: {result.status}"
            )
        result.status = KYCStatus.APPROVED
        result.mlro_sign_off = True
        result.updated_at = self._now()
        result.notes.append(
            f"EDD approved by MLRO: {mlro_user_id} at {result.updated_at.isoformat()}"
        )
        return result

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        """Reject workflow at any non-terminal stage."""
        result = self._workflows.get(workflow_id)
        if result is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        if result.is_terminal:
            raise ValueError(f"Workflow {workflow_id} already in terminal state {result.status}")
        result.status = KYCStatus.REJECTED
        result.rejection_reason = reason
        result.updated_at = self._now()
        result.notes.append(f"Rejected: {reason.value}")
        return result

    def health(self) -> bool:
        return True


_bl_logger = _logging.getLogger(__name__)


# ── Ballerine status → KYCStatus mapping ─────────────────────────────────────

_BALLERINE_STATUS_MAP: dict[str, KYCStatus] = {
    # Workflow runtime states
    "created":            KYCStatus.PENDING,
    "active":             KYCStatus.DOCUMENT_REVIEW,
    "pending":            KYCStatus.PENDING,
    "document_review":    KYCStatus.DOCUMENT_REVIEW,
    "risk_assessment":    KYCStatus.RISK_ASSESSMENT,
    "edd_required":       KYCStatus.EDD_REQUIRED,
    "manual_review":      KYCStatus.MLRO_REVIEW,
    "mlro_review":        KYCStatus.MLRO_REVIEW,
    "approved":           KYCStatus.APPROVED,
    "completed":          KYCStatus.APPROVED,   # check result field below
    "rejected":           KYCStatus.REJECTED,
    "failed":             KYCStatus.REJECTED,
    "expired":            KYCStatus.EXPIRED,
}

_REJECTION_REASON_MAP: dict[str, RejectionReason] = {
    "SANCTIONS_HIT":          RejectionReason.SANCTIONS_HIT,
    "DOCUMENT_FRAUD":         RejectionReason.DOCUMENT_FRAUD,
    "HIGH_RISK_JURISDICTION": RejectionReason.HIGH_RISK_JURISDICTION,
    "PEP_NO_EDD":             RejectionReason.PEP_NO_EDD,
    "RISK_SCORE_TOO_HIGH":    RejectionReason.RISK_SCORE_TOO_HIGH,
    "INCOMPLETE_DOCUMENTS":   RejectionReason.INCOMPLETE_DOCUMENTS,
    "AML_PATTERN":            RejectionReason.AML_PATTERN,
}


class BallerineAdapter:
    """
    Live Ballerine KYC orchestration adapter.
    Connects to a self-hosted Ballerine workflow-service via REST API.

    Prerequisites:
        docker compose -f infra/ballerine/docker-compose.yml up
        Set BALLERINE_URL=http://gmktec:3000 in .env
        Set BALLERINE_KYC_DEFINITION_ID and BALLERINE_KYB_DEFINITION_ID

    Ballerine API:
        POST /api/v1/end-users        — create end user
        POST /api/v1/workflows/run    — start a workflow
        GET  /api/v1/workflows/{id}   — get workflow state
        PATCH /api/v1/workflows/{id}/event — send workflow event
        GET  /api/v1/health           — health check
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        kyc_definition_id: Optional[str] = None,
        kyb_definition_id: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        import os
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            raise RuntimeError("httpx not installed: pip install httpx")

        self._base_url = (base_url or os.environ.get("BALLERINE_URL", "")).rstrip("/")
        if not self._base_url:
            raise EnvironmentError(
                "BALLERINE_URL not set. "
                "Deploy Ballerine: docker compose -f infra/ballerine/docker-compose.yml up"
            )
        self._kyc_def_id = (
            kyc_definition_id
            or os.environ.get("BALLERINE_KYC_DEFINITION_ID", "banxe-individual-kyc-v1")
        )
        self._kyb_def_id = (
            kyb_definition_id
            or os.environ.get("BALLERINE_KYB_DEFINITION_ID", "banxe-business-kyb-v1")
        )
        headers = {"Content-Type": "application/json"}
        token = api_token or os.environ.get("BALLERINE_API_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _parse_workflow(self, data: dict) -> KYCWorkflowResult:
        """Map Ballerine workflow runtime JSON → KYCWorkflowResult."""
        from datetime import timezone
        raw_status = data.get("status", "").lower()
        # If completed, check result context for approved/rejected
        if raw_status == "completed":
            ctx = data.get("context", {})
            result = ctx.get("result", "").lower()
            if result == "rejected":
                raw_status = "rejected"

        status = _BALLERINE_STATUS_MAP.get(raw_status, KYCStatus.PENDING)

        ctx = data.get("context", {})
        rejection_raw = ctx.get("rejectionReason") or ctx.get("rejection_reason")
        rejection: Optional[RejectionReason] = None
        if rejection_raw:
            rejection = _REJECTION_REASON_MAP.get(str(rejection_raw).upper())

        edd_required = status in (
            KYCStatus.EDD_REQUIRED, KYCStatus.MLRO_REVIEW
        ) or bool(ctx.get("eddRequired", False))

        created_at_raw = data.get("createdAt") or data.get("created_at", "")
        updated_at_raw = data.get("updatedAt") or data.get("updated_at", "")
        expires_at_raw = data.get("expiresAt") or data.get("expires_at", "")

        now = datetime.now(timezone.utc)

        def _parse_dt(raw: str) -> datetime:
            if not raw:
                return now
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return now

        entity = data.get("entity", {}) or {}
        customer_id = (
            ctx.get("customerId")
            or ctx.get("customer_id")
            or entity.get("id", "")
            or data.get("id", "")
        )

        kyc_type = KYCType.INDIVIDUAL
        if (entity.get("type", "") or "").upper() in ("BUSINESS", "COMPANY"):
            kyc_type = KYCType.BUSINESS

        return KYCWorkflowResult(
            workflow_id=str(data.get("id", "")),
            customer_id=customer_id,
            status=status,
            kyc_type=kyc_type,
            created_at=_parse_dt(created_at_raw),
            updated_at=_parse_dt(updated_at_raw),
            expires_at=_parse_dt(expires_at_raw) if expires_at_raw else (
                _parse_dt(created_at_raw) + timedelta(days=_WORKFLOW_TTL_DAYS)
                if created_at_raw else now
            ),
            edd_required=edd_required,
            rejection_reason=rejection,
            risk_score=ctx.get("riskScore") or ctx.get("risk_score"),
            notes=ctx.get("notes") or [],
            mlro_sign_off=bool(ctx.get("mlroSignOff", False)),
        )

    def _raise_for_status(self, response: object, action: str) -> dict:
        if response.is_error:
            raise RuntimeError(
                f"Ballerine API error [{action}]: "
                f"{response.status_code} — {response.text[:200]}"
            )
        return response.json()

    # ── KYCWorkflowPort interface ─────────────────────────────────────────────

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """
        Create a Ballerine end-user then start a KYC/KYB workflow run.
        Ballerine: POST /api/v1/end-users → POST /api/v1/workflows/run
        """
        # 1. Create end user
        entity_type = "individual" if request.kyc_type == KYCType.INDIVIDUAL else "business"
        end_user_payload: dict = {
            "firstName": request.first_name,
            "lastName": request.last_name,
            "dateOfBirth": request.date_of_birth,
            "nationalId": request.customer_id,
            "additionalInfo": {
                "customerId": request.customer_id,
                "nationality": request.nationality,
                "countryOfResidence": request.country_of_residence,
                "isPep": request.is_pep,
                "expectedTransactionVolume": str(request.expected_transaction_volume),
            },
        }
        if entity_type == "business" and request.business_name:
            end_user_payload["business"] = {
                "companyName": request.business_name,
                "registrationNumber": request.registration_number or "",
            }

        end_user_resp = self._client.post("/api/v1/end-users", json=end_user_payload)
        end_user_data = self._raise_for_status(end_user_resp, "create_end_user")
        end_user_id = end_user_data.get("id", "")

        # 2. Run workflow
        definition_id = (
            self._kyc_def_id if request.kyc_type == KYCType.INDIVIDUAL
            else self._kyb_def_id
        )
        wf_payload = {
            "workflowDefinitionId": definition_id,
            "endUserId": end_user_id,
            "context": {
                "customerId": request.customer_id,
                "entity": {"id": end_user_id, "type": entity_type},
            },
        }
        wf_resp = self._client.post("/api/v1/workflows/run", json=wf_payload)
        wf_data = self._raise_for_status(wf_resp, "create_workflow")
        result = self._parse_workflow(wf_data)
        # Preserve customerId from request (Ballerine may return end_user_id instead)
        result.customer_id = request.customer_id
        _bl_logger.info(
            "Ballerine workflow created: %s → %s (customer=%s)",
            result.workflow_id, result.status, request.customer_id,
        )
        return result

    def get_workflow(self, workflow_id: str) -> Optional[KYCWorkflowResult]:
        """GET /api/v1/workflows/{id} — returns None if not found."""
        resp = self._client.get(f"/api/v1/workflows/{workflow_id}")
        if resp.status_code == 404:
            return None
        data = self._raise_for_status(resp, "get_workflow")
        return self._parse_workflow(data)

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        """
        Signal to Ballerine that documents are ready for review.
        PATCH /api/v1/workflows/{id}/event → event: DOCUMENTS_SUBMITTED
        """
        payload = {
            "name": "DOCUMENTS_SUBMITTED",
            "payload": {"documentIds": document_ids},
        }
        resp = self._client.patch(
            f"/api/v1/workflows/{workflow_id}/event", json=payload
        )
        data = self._raise_for_status(resp, "submit_documents")
        result = self._parse_workflow(data)
        _bl_logger.info(
            "Ballerine docs submitted: workflow=%s docs=%s status=%s",
            workflow_id, document_ids, result.status,
        )
        return result

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """
        MLRO approves EDD — moves workflow to APPROVED.
        PATCH /api/v1/workflows/{id}/event → event: APPROVE
        FCA MLR 2017 §33: MLRO sign-off required for EDD.
        """
        payload = {
            "name": "MANUAL_REVIEW_APPROVE",
            "payload": {"mlroUserId": mlro_user_id},
        }
        resp = self._client.patch(
            f"/api/v1/workflows/{workflow_id}/event", json=payload
        )
        data = self._raise_for_status(resp, "approve_edd")
        result = self._parse_workflow(data)
        result.mlro_sign_off = True
        _bl_logger.warning(
            "Ballerine EDD approved: workflow=%s by_mlro=%s status=%s",
            workflow_id, mlro_user_id, result.status,
        )
        return result

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        """
        Reject KYC workflow (sanctions hit, fraud, risk too high).
        PATCH /api/v1/workflows/{id}/event → event: REJECT
        """
        payload = {
            "name": "MANUAL_REVIEW_REJECT",
            "payload": {"rejectionReason": reason.value},
        }
        resp = self._client.patch(
            f"/api/v1/workflows/{workflow_id}/event", json=payload
        )
        data = self._raise_for_status(resp, "reject_workflow")
        result = self._parse_workflow(data)
        result.rejection_reason = reason
        _bl_logger.warning(
            "Ballerine workflow rejected: workflow=%s reason=%s",
            workflow_id, reason.value,
        )
        return result

    def health(self) -> bool:
        """GET /api/v1/health — True if Ballerine is reachable and healthy."""
        try:
            resp = self._client.get("/api/v1/health", timeout=5)
            return resp.status_code == 200
        except Exception as exc:
            _bl_logger.warning("Ballerine health check failed: %s", exc)
            return False


def get_kyc_adapter() -> KYCWorkflowPort:
    """Factory: KYC_ADAPTER=mock (default) | ballerine."""
    import os
    adapter = os.environ.get("KYC_ADAPTER", "mock").lower()
    if adapter == "ballerine":
        return BallerineAdapter()
    return MockKYCWorkflow()
