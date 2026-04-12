"""
services/case_management/marble_adapter.py — Marble Case Management Adapter (IL-059)
CaseManagementPort implementation for Marble (self-hosted, Apache 2.0)
EU AI Act Art.14 (human oversight) | FCA MLR 2017 §26 | banxe-emi-stack

WHY THIS EXISTS
---------------
Marble (https://checkmarble.com) is an open-source transaction monitoring and
case management platform deployed on GMKtec (:5002). It provides:
  - MLRO inbox with case assignment
  - Case status tracking (OPEN → INVESTIGATING → RESOLVED)
  - Audit trail for FCA and EU AI Act compliance
  - Integration with decision engine (can receive Jube/Sardine decisions)

Authentication:
  Marble uses API key auth via Authorization: Bearer {MARBLE_API_KEY} header.
  API key is configured in Marble admin UI and set in MARBLE_API_KEY env var.

Key endpoints:
  POST   /api/cases                 → create case
  GET    /api/cases/{id}            → get case
  PATCH  /api/cases/{id}            → update case (status, outcome)
  GET    /api/health                → health check

Case fields (Marble API):
  name          — human-readable title (shown in MLRO inbox)
  description   — detailed narrative for compliance team
  inboxId       — Marble inbox GUID (MARBLE_INBOX_ID env var)
  status        — "open" | "investigating" | "resolved" | "closed"
  outcome       — "approved" | "rejected" | "escalated" | "inconclusive"

Required environment variables:
  MARBLE_URL       — http://gmktec:5002
  MARBLE_API_KEY   — Marble API key from admin UI
  MARBLE_INBOX_ID  — Default MLRO inbox GUID (created in Marble admin UI)
  MARBLE_TIMEOUT_MS — HTTP timeout ms (default: 5000)
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os

from services.case_management.case_port import (
    CaseOutcome,
    CaseRequest,
    CaseResult,
    CaseStatus,
)

logger = logging.getLogger(__name__)

_MARBLE_CASES_PATH = "/api/cases"
_MARBLE_HEALTH_PATH = "/api/health"

# Marble status string → CaseStatus enum
_STATUS_MAP = {
    "open": CaseStatus.OPEN,
    "investigating": CaseStatus.INVESTIGATING,
    "resolved": CaseStatus.RESOLVED,
    "closed": CaseStatus.CLOSED,
}

# CaseOutcome enum → Marble outcome string
_OUTCOME_MAP = {
    CaseOutcome.APPROVED: "approved",
    CaseOutcome.REJECTED: "rejected",
    CaseOutcome.ESCALATED: "escalated",
    CaseOutcome.INCONCLUSIVE: "inconclusive",
}


class MarbleAdapter:
    """
    Live Marble case management adapter.
    Satisfies CaseManagementPort. Self-hosted on GMKtec :5002.

    Usage:
        # Set env vars: MARBLE_URL, MARBLE_API_KEY, MARBLE_INBOX_ID
        adapter = MarbleAdapter()
        result = adapter.create_case(request)

    Idempotency: Marble does not natively deduplicate on case_reference.
    This adapter stores case_reference in Marble case metadata; callers
    should track case_id after creation to avoid duplicates.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        inbox_id: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        try:
            import importlib.util

            if importlib.util.find_spec("httpx") is None:
                raise ImportError
        except ImportError:
            raise RuntimeError("httpx not installed: pip install httpx")

        self._base_url = (base_url or os.environ.get("MARBLE_URL", "")).rstrip("/")
        if not self._base_url:
            raise OSError(
                "MARBLE_URL not set. "
                "Marble is deployed on GMKtec at http://gmktec:5002. "
                "Set MARBLE_URL=http://gmktec:5002 in .env"
            )

        self._api_key = api_key or os.environ.get("MARBLE_API_KEY", "")
        if not self._api_key:
            raise OSError(
                "MARBLE_API_KEY not set. "
                "Create an API key in the Marble admin UI (http://gmktec:5002), "
                "then set MARBLE_API_KEY in .env"
            )

        self._inbox_id = inbox_id or os.environ.get("MARBLE_INBOX_ID", "")
        if not self._inbox_id:
            raise OSError(
                "MARBLE_INBOX_ID not set. "
                "Create an inbox in the Marble admin UI (http://gmktec:5002), "
                "then copy its ID to MARBLE_INBOX_ID in .env"
            )

        _timeout_ms = timeout_ms or int(os.environ.get("MARBLE_TIMEOUT_MS", "5000"))
        self._timeout_s = _timeout_ms / 1000.0

        import httpx as _httpx

        self._httpx = _httpx
        self._client = _httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_s,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    # ── CaseManagementPort interface ──────────────────────────────────────────

    def create_case(self, request: CaseRequest) -> CaseResult:
        """
        POST /api/cases → open a new Marble case.

        The case_reference is stored in Marble's metadata field so MLRO can
        trace back to the originating Banxe transaction.
        """
        payload = self._build_create_payload(request)

        try:
            resp = self._client.post(_MARBLE_CASES_PATH, json=payload)
        except self._httpx.TimeoutException:
            logger.error(
                "Marble timeout creating case ref=%s — returning stub",
                request.case_reference,
            )
            return self._stub_result(request.case_reference, "marble_timeout")

        if resp.is_error:
            logger.error(
                "Marble create_case error: ref=%s status=%d body=%s",
                request.case_reference,
                resp.status_code,
                resp.text[:200],
            )
            return self._stub_result(request.case_reference, "marble_error")

        data = resp.json()
        result = self._parse_case(data, request.case_reference)
        logger.info(
            "Marble case created: ref=%s case_id=%s status=%s",
            request.case_reference,
            result.case_id,
            result.status,
        )
        return result

    def get_case(self, case_id: str) -> CaseResult:
        """GET /api/cases/{id} → current case state."""
        try:
            resp = self._client.get(f"{_MARBLE_CASES_PATH}/{case_id}")
        except self._httpx.TimeoutException:
            logger.error("Marble timeout getting case_id=%s", case_id)
            return self._stub_result(case_id, "marble_timeout")

        if resp.is_error:
            logger.error(
                "Marble get_case error: case_id=%s status=%d",
                case_id,
                resp.status_code,
            )
            return self._stub_result(case_id, "marble_error")

        return self._parse_case(resp.json(), case_id)

    def resolve_case(
        self,
        case_id: str,
        outcome: CaseOutcome,
        notes: str = "",
    ) -> CaseResult:
        """
        PATCH /api/cases/{id} → set status=resolved + outcome.
        I-27: outcome is always set by a human; this method is called AFTER
        the MLRO has made their decision in the Marble backoffice.
        """
        payload: dict = {
            "status": "resolved",
            "outcome": _OUTCOME_MAP.get(outcome, "inconclusive"),
        }
        if notes:
            payload["comment"] = notes

        try:
            resp = self._client.patch(f"{_MARBLE_CASES_PATH}/{case_id}", json=payload)
        except self._httpx.TimeoutException:
            logger.error("Marble timeout resolving case_id=%s", case_id)
            return self._stub_result(case_id, "marble_timeout")

        if resp.is_error:
            logger.error(
                "Marble resolve_case error: case_id=%s status=%d body=%s",
                case_id,
                resp.status_code,
                resp.text[:200],
            )
            return self._stub_result(case_id, "marble_error")

        result = self._parse_case(resp.json(), case_id)
        logger.info(
            "Marble case resolved: case_id=%s outcome=%s",
            case_id,
            outcome,
        )
        return result

    def health(self) -> bool:
        """GET /api/health → True if Marble is reachable."""
        try:
            resp = self._client.get(_MARBLE_HEALTH_PATH)
            return resp.status_code < 500
        except Exception as exc:
            logger.warning("Marble health check failed: %s", exc)
            return False

    # ── Payload builder ───────────────────────────────────────────────────────

    def _build_create_payload(self, request: CaseRequest) -> dict:
        """
        Build Marble POST /api/cases request body.
        Field names match Marble API spec (camelCase).
        """
        description_parts = [request.description]
        if request.risk_score is not None:
            description_parts.append(f"Risk score: {request.risk_score}/100")
        if request.amount is not None:
            description_parts.append(f"Amount: {request.amount} {request.currency or ''}")

        return {
            "name": f"[{request.case_type.value}] {request.case_reference}",
            "description": "\n".join(description_parts),
            "inboxId": self._inbox_id,
            "status": "open",
            "metadata": {
                "banxe_reference": request.case_reference,
                "case_type": request.case_type.value,
                "entity_id": request.entity_id,
                "entity_type": request.entity_type,
                "priority": request.priority.value,
                **request.metadata,
            },
        }

    # ── Response parser ───────────────────────────────────────────────────────

    def _parse_case(self, data: dict, fallback_reference: str) -> CaseResult:
        """
        Map Marble API case response → CaseResult.
        Marble returns camelCase JSON.
        """
        case_id = data.get("id") or data.get("caseId") or fallback_reference
        status_raw = (data.get("status") or "open").lower()
        status = _STATUS_MAP.get(status_raw, CaseStatus.OPEN)

        outcome_raw = (data.get("outcome") or "").lower()
        outcome_map_inv = {v: k for k, v in _OUTCOME_MAP.items()}
        outcome = outcome_map_inv.get(outcome_raw)

        metadata = data.get("metadata") or {}
        case_reference = (
            metadata.get("banxe_reference") or data.get("name", "") or fallback_reference
        )

        created_at_raw = data.get("createdAt") or data.get("created_at") or ""
        try:
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(UTC)

        assigned_to = (
            data.get("assignedTo")
            or data.get("assigned_to")
            or (data.get("assignee") or {}).get("email")
        )

        marble_url = data.get("url") or (f"{self._base_url}/cases/{case_id}" if case_id else None)

        return CaseResult(
            case_id=str(case_id),
            case_reference=case_reference,
            status=status,
            provider="marble",
            created_at=created_at,
            assigned_to=assigned_to,
            outcome=outcome,
            url=marble_url,
        )

    # ── Fallback ──────────────────────────────────────────────────────────────

    def _stub_result(self, reference: str, reason: str) -> CaseResult:
        """Conservative stub on timeout/error: case appears as OPEN for MLRO review."""
        return CaseResult(
            case_id=f"STUB-{reason.upper()}",
            case_reference=reference,
            status=CaseStatus.OPEN,
            provider=f"marble_{reason}",
            created_at=datetime.now(UTC),
            url=None,
        )
