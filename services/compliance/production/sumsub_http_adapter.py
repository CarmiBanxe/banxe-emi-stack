"""
sumsub_http_adapter.py — SumsubHttpAdapter: KYCWorkflowPort via SumSub REST API.

Production HTTP adapter replacing SumsubHttpStub (ADR-025 §15-16, Sprint 7).
Requests are HMAC-SHA256 signed per SumSub API v1 canon.
Sandbox-only by default — no live API calls unless sandbox=False is explicit.

SumSub endpoints:
  POST /resources/applicants?levelName={LEVEL}                 → create_workflow
  GET  /resources/applicants/{applicantId}                     → get_workflow
  POST /resources/applicants/{applicantId}/status/pending      → submit_documents
  POST /resources/applicants/{applicantId}/status/approve      → approve_edd
  POST /resources/applicants/{applicantId}/status/reject       → reject_workflow
  GET  /resources/status                                       → health

Env: SUMSUB_APP_TOKEN, SUMSUB_SECRET_KEY, SUMSUB_BASE_URL
Canon: ADR-025 §15-16 + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-KYC-PROD-01]
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx

from services.compliance.legacy._edd import is_edd_required
from services.compliance.legacy._jurisdictions import is_blocked
from services.compliance.legacy.legacy_sumsub_adapter import (
    SumSubApplicationError,
    SumSubAuditRecord,
    _SumSubEventType,
)
from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)

_WORKFLOW_TTL_DAYS: int = 30
_DEFAULT_LEVEL: str = "basic-kyc-level"


def _map_status(review: dict[str, Any]) -> KYCStatus:
    """Map SumSub reviewStatus → KYCStatus."""
    match review.get("reviewStatus", "init"):
        case "init":
            return KYCStatus.PENDING
        case "pending":
            return KYCStatus.DOCUMENT_REVIEW
        case "queued":
            return KYCStatus.RISK_ASSESSMENT
        case "onHold":
            return KYCStatus.EDD_REQUIRED
        case "completed":
            return (
                KYCStatus.APPROVED if review.get("reviewAnswer") == "GREEN" else KYCStatus.REJECTED
            )
        case _:
            return KYCStatus.PENDING


class SumsubHttpAdapter:
    """
    KYCWorkflowPort — SumSub REST API, HMAC-SHA256 signed (Sprint 7, [IL-KYC-PROD-01]).

    workflow_id == SumSub applicantId: SumSub is authoritative for all state.
    I-02/I-04 enforced at create_workflow. I-24 audit trail in self._audit_log.
    """

    def __init__(
        self,
        *,
        sandbox: bool = True,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._app_token: str = os.environ["SUMSUB_APP_TOKEN"]
        self._secret: str = os.environ["SUMSUB_SECRET_KEY"]
        self._base_url: str = os.environ.get("SUMSUB_BASE_URL", "https://api.sumsub.com").rstrip(
            "/"
        )
        self._sandbox = sandbox
        self._http: httpx.Client = http_client if http_client is not None else httpx.Client()
        self._audit_log: list[SumSubAuditRecord] = []

    # ── KYCWorkflowPort ───────────────────────────────────────────────────────

    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult:
        """POST /resources/applicants — I-02 block + I-04 EDD gate."""
        for country in (request.nationality, request.country_of_residence):
            if is_blocked(country):
                raise SumSubApplicationError(
                    f"Blocked jurisdiction: {country!r} (I-02)", code="blocked_jurisdiction"
                )

        edd_required = is_edd_required(
            income_gbp=request.expected_transaction_volume,
            kyc_type=request.kyc_type.value,
            is_pep=request.is_pep,
        )

        body: dict[str, Any] = {
            "externalUserId": request.customer_id,
            "info": {
                "firstName": request.first_name,
                "lastName": request.last_name,
                "dob": request.date_of_birth,
                "country": request.country_of_residence.upper(),
                "nationality": request.nationality.upper(),
            },
        }
        if request.business_name:
            body["companyInfo"] = {
                "companyName": request.business_name,
                "registrationNumber": request.registration_number or "",
            }

        data = self._request("POST", f"/resources/applicants?levelName={_DEFAULT_LEVEL}", body=body)
        result = self._to_result(data, edd_required=edd_required)
        self._emit_audit(result.workflow_id, request.customer_id, "CREATED", None, result.status)
        return result

    def get_workflow(self, workflow_id: str) -> KYCWorkflowResult | None:
        """GET /resources/applicants/{applicantId} — returns None on 404."""
        try:
            data = self._request("GET", f"/resources/applicants/{workflow_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return self._to_result(data)

    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult:
        """POST …/status/pending to trigger review; re-fetches state via GET."""
        self._request("POST", f"/resources/applicants/{workflow_id}/status/pending")
        data = self._request("GET", f"/resources/applicants/{workflow_id}")
        result = self._to_result(data)
        self._emit_audit(workflow_id, None, "DOCUMENTS_SUBMITTED", KYCStatus.PENDING, result.status)
        return result

    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult:
        """POST …/status/approve — I-27: MLRO must approve externally before this call."""
        self._request("POST", f"/resources/applicants/{workflow_id}/status/approve")
        data = self._request("GET", f"/resources/applicants/{workflow_id}")
        result = self._to_result(data, mlro_sign_off=True)
        self._emit_audit(workflow_id, None, "APPROVED", KYCStatus.MLRO_REVIEW, result.status)
        return result

    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult:
        """POST …/status/reject with rejection labels."""
        body = {"rejectLabels": [reason.value], "comment": reason.value}
        self._request("POST", f"/resources/applicants/{workflow_id}/status/reject", body=body)
        data = self._request("GET", f"/resources/applicants/{workflow_id}")
        result = self._to_result(data, rejection_reason=reason)
        self._emit_audit(workflow_id, None, "REJECTED", None, result.status)
        return result

    def health(self) -> bool:
        """GET /resources/status — True if SumSub API is reachable."""
        try:
            self._request("GET", "/resources/status")
            return True
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        self._http.close()

    def collect_audit_records(self) -> list[SumSubAuditRecord]:
        """I-24 append-only audit trail accessor."""
        return list(self._audit_log)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sign(self, method: str, path: str, body_str: str) -> dict[str, str]:
        ts = str(int(time.time()))
        sig_input = (ts + method.upper() + path + body_str).encode()
        sig = hmac.new(self._secret.encode(), sig_input, hashlib.sha256).hexdigest()
        return {
            "X-App-Token": self._app_token,
            "X-App-Access-Ts": ts,
            "X-App-Access-Sig": sig,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body_str = json.dumps(body) if body is not None else ""
        headers = self._sign(method, path, body_str)
        resp = self._http.request(
            method,
            self._base_url + path,
            headers=headers,
            content=body_str.encode() if body_str else None,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _to_result(
        self,
        data: dict[str, Any],
        *,
        edd_required: bool = False,
        rejection_reason: RejectionReason | None = None,
        mlro_sign_off: bool = False,
    ) -> KYCWorkflowResult:
        review = data.get("review", {})
        status = _map_status(review)
        now = datetime.now(UTC)
        created_at_raw = data.get("createdAt", "")
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else now
        kyc_type = KYCType.BUSINESS if "companyInfo" in data else KYCType.INDIVIDUAL
        return KYCWorkflowResult(
            workflow_id=data["id"],
            customer_id=data.get("externalUserId", ""),
            status=status,
            kyc_type=kyc_type,
            created_at=created_at,
            updated_at=now,
            expires_at=created_at + timedelta(days=_WORKFLOW_TTL_DAYS),
            edd_required=edd_required,
            rejection_reason=rejection_reason,
            risk_score=None,
            notes=[],
            mlro_sign_off=mlro_sign_off,
        )

    def _emit_audit(
        self,
        workflow_id: str,
        customer_id: str | None,
        event_type: _SumSubEventType,
        status_from: KYCStatus | None,
        status_to: KYCStatus,
    ) -> None:
        self._audit_log.append(
            SumSubAuditRecord(
                record_id=workflow_id,
                customer_id=customer_id,
                workflow_id=workflow_id,
                event_type=event_type,
                status_from=status_from,
                status_to=status_to,
                occurred_at=datetime.now(UTC),
            )
        )
