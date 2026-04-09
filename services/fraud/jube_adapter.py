"""
services/fraud/jube_adapter.py — Jube Fraud Rules Engine Adapter (IL-057)
FraudScoringPort implementation for Jube (self-hosted, AGPLv3)
S5-22 (<100ms SLA) | PSR APP 2024 | FCA MLR 2017 Reg.26 | banxe-emi-stack

WHY THIS EXISTS
---------------
Jube (https://jube-home.github.io) is an open-source, self-hosted AML/Fraud
transaction monitoring engine deployed on GMKtec (:5001). It provides:
  - Rules-based activation engine (FCA-auditable decision trail)
  - Case management with audit trail
  - ML-assisted risk scoring
  - FCA-required audit log (I-24: append-only, TTL ≥ 5 years)

Unlike Sardine.ai (external API key required), Jube runs locally with no
external API key. JubeAdapter replaces MockFraudAdapter for production use.

Authentication:
  POST /api/Authentication/ByUserNamePassword → JWT Bearer token
  Token is cached and refreshed 60 seconds before expiry (I-27 pattern).

Invocation:
  POST /api/Invoke/EntityAnalysisModel/{model_guid}
  - model_guid: GUID of the configured EntityAnalysisModel in Jube
  - Body: flat JSON with named fields matching model's XPath definitions
  - Response: computed scores, activation rules, tags, audit GUID

Score mapping → FraudRisk:
  responseElevation 0-100 (Jube) → FraudRisk (same thresholds as MockFraudAdapter)
  ≥ 85 → CRITICAL (block)
  70-84 → HIGH (HITL hold, FCA MLRO review)
  40-69 → MEDIUM (enhanced checks)
  0-39  → LOW

Required environment variables:
  JUBE_URL          — http://gmktec:5001
  JUBE_USERNAME     — Jube admin username (default: Administrator)
  JUBE_PASSWORD     — Jube admin password (set during deploy)
  JUBE_MODEL_GUID   — EntityAnalysisModel GUID from Jube admin UI
  JUBE_TIMEOUT_MS   — HTTP timeout ms (default: 90, hard SLA is 100ms)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime, timedelta

from services.fraud.fraud_port import (
    AppScamIndicator,
    FraudRisk,
    FraudScoringRequest,
    FraudScoringResult,
)

logger = logging.getLogger(__name__)

# Jube response elevation → FraudRisk thresholds (aligned with MockFraudAdapter + AML pipeline)
_SCORE_CRITICAL = 85
_SCORE_HIGH = 70
_SCORE_MEDIUM = 40

# JWT refresh margin — re-auth 60s before expiry
_JWT_REFRESH_MARGIN_S = 60

# Jube uses PascalCase JSON field names (ASP.NET Core default)
_JUBE_AUTH_PATH = "/api/Authentication/ByUserNamePassword"
_JUBE_INVOKE_PATH = "/api/Invoke/EntityAnalysisModel/{guid}"
_JUBE_HEALTH_PATH = "/api/EntityAnalysisModel"


class JubeAdapter:
    """
    Live Jube fraud rules engine adapter.
    Satisfies FraudScoringPort. Self-hosted on GMKtec.

    Usage:
        # Set env vars: JUBE_URL, JUBE_USERNAME, JUBE_PASSWORD, JUBE_MODEL_GUID
        adapter = JubeAdapter()
        result = adapter.score(request)

    Thread safety: lazy JWT auth is not thread-safe under concurrent initialisation.
    In production, use a process-level singleton (one per worker process).
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        model_guid: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        try:
            import importlib.util

            if importlib.util.find_spec("httpx") is None:
                raise ImportError
        except ImportError:
            raise RuntimeError("httpx not installed: pip install httpx")

        self._base_url = (base_url or os.environ.get("JUBE_URL", "")).rstrip("/")
        if not self._base_url:
            raise OSError(
                "JUBE_URL not set. "
                "Jube is deployed on GMKtec at http://gmktec:5001. "
                "Set JUBE_URL=http://gmktec:5001 in .env"
            )

        self._username = username or os.environ.get("JUBE_USERNAME", "Administrator")
        self._password = password or os.environ.get("JUBE_PASSWORD", "")
        if not self._password:
            raise OSError(
                "JUBE_PASSWORD not set. "
                "Set JUBE_PASSWORD in .env (see Jube admin UI for the Administrator password)."
            )

        self._model_guid = model_guid or os.environ.get("JUBE_MODEL_GUID", "")
        if not self._model_guid:
            raise OSError(
                "JUBE_MODEL_GUID not set. "
                "Create an EntityAnalysisModel in the Jube admin UI (http://gmktec:5001), "
                "then copy its GUID to JUBE_MODEL_GUID in .env"
            )

        _timeout_ms = timeout_ms or int(os.environ.get("JUBE_TIMEOUT_MS", "90"))
        self._timeout_s = _timeout_ms / 1000.0

        import httpx as _httpx

        self._httpx = _httpx
        self._client = _httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_s,
        )

        self._jwt: str | None = None
        self._jwt_expires_at: datetime | None = None

    # ── Authentication ────────────────────────────────────────────────────────

    def _authenticate(self) -> str:
        """
        POST /api/Authentication/ByUserNamePassword → JWT Bearer token.
        Raises RuntimeError on 401 (wrong credentials) or HTTP error.
        """
        resp = self._client.post(
            _JUBE_AUTH_PATH,
            json={"UserName": self._username, "Password": self._password},
        )
        if resp.status_code == 401:
            raise RuntimeError(
                "Jube authentication failed: 401 Unauthorized. "
                "Check JUBE_USERNAME and JUBE_PASSWORD in .env."
            )
        if resp.is_error:
            raise RuntimeError(f"Jube authentication error: {resp.status_code} — {resp.text[:200]}")
        data = resp.json()
        # Jube returns: {"token": "...", "tokenExpiryTime": "2026-..."}
        token = data.get("token") or data.get("Token") or ""
        if not token:
            raise RuntimeError(f"Jube auth response missing token: {data}")

        # Parse expiry; fall back to 1 hour if missing
        expiry_raw = data.get("tokenExpiryTime") or data.get("TokenExpiryTime") or ""
        try:
            expiry = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            expiry = datetime.now(UTC) + timedelta(hours=1)

        self._jwt = token
        self._jwt_expires_at = expiry
        logger.info("Jube JWT obtained, expires: %s", expiry.isoformat())
        return token

    def _get_jwt(self) -> str:
        """Return cached JWT, re-authenticating if expired or about to expire."""
        now = datetime.now(UTC)
        margin = timedelta(seconds=_JWT_REFRESH_MARGIN_S)
        if self._jwt and self._jwt_expires_at and now < self._jwt_expires_at - margin:
            return self._jwt
        return self._authenticate()

    # ── Scoring ───────────────────────────────────────────────────────────────

    def score(self, request: FraudScoringRequest) -> FraudScoringResult:
        """
        Invoke Jube EntityAnalysisModel → FraudScoringResult.

        POST /api/Invoke/EntityAnalysisModel/{model_guid}
        Body: flat JSON with transaction fields (mapped to Jube XPath definitions).
        Response: responseElevation (0-100) + activation rule booleans + tags.

        SLA: S5-22 requires < 100ms. JUBE_TIMEOUT_MS defaults to 90ms.
        """
        t0 = time.monotonic()
        jwt = self._get_jwt()
        payload = self._build_payload(request)
        url = _JUBE_INVOKE_PATH.replace("{guid}", self._model_guid)

        try:
            resp = self._client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {jwt}"},
            )
        except self._httpx.TimeoutException:
            logger.error(
                "Jube timeout (>%dms): tx=%s — falling back to mock score",
                int(self._timeout_s * 1000),
                request.transaction_id,
            )
            return self._timeout_fallback(request, time.monotonic() - t0)

        latency_ms = (time.monotonic() - t0) * 1000

        if resp.status_code == 401:
            # Token may have expired mid-flight — re-auth once and retry
            self._jwt = None
            jwt = self._get_jwt()
            resp = self._client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {jwt}"},
            )

        if resp.is_error:
            logger.error(
                "Jube invoke error: tx=%s status=%d body=%s",
                request.transaction_id,
                resp.status_code,
                resp.text[:200],
            )
            return self._error_fallback(request, latency_ms)

        result = self._parse_response(request, resp.json(), latency_ms)
        logger.info(
            "Jube scored: tx=%s score=%d risk=%s latency=%.1fms",
            request.transaction_id,
            result.score,
            result.risk.value,
            latency_ms,
        )
        return result

    # ── Payload builder ───────────────────────────────────────────────────────

    def _build_payload(self, request: FraudScoringRequest) -> dict:
        """
        Build the JSON payload for Jube EntityAnalysisModel invocation.

        Field names must match the EntityAnalysisModelRequestXPath 'name' values
        configured in the Jube model. These are the canonical Banxe field names;
        update JUBE_MODEL_GUID and XPath definitions in the Jube UI if they differ.

        All monetary amounts are Decimal → str (I-05).
        """
        return {
            "TransactionId": request.transaction_id,
            "CustomerId": request.customer_id,
            "TransactionAmount": str(request.amount),  # I-05: string, not float
            "Currency": request.currency,
            "DestinationAccount": request.destination_account,
            "DestinationSortCode": request.destination_sort_code,
            "DestinationCountry": request.destination_country,
            "PaymentRail": request.payment_rail,
            "EntityType": request.entity_type,
            "FirstTransactionToPayee": request.first_transaction_to_payee,
            "AmountUnusual": request.amount_unusual,
            "CustomerIp": request.customer_ip or "",
            "CustomerDeviceId": request.customer_device_id or "",
            "SessionId": request.session_id or "",
        }

    # ── Response parser ───────────────────────────────────────────────────────

    def _parse_response(
        self,
        request: FraudScoringRequest,
        data: dict,
        latency_ms: float,
    ) -> FraudScoringResult:
        """
        Map Jube invoke response → FraudScoringResult.

        Jube returns a flat dict with:
          - "ResponseElevation" or "responseElevation": int/float 0-100
          - Boolean activation rule fields (e.g. "BlockTransaction", "HoldForReview")
          - "EntityAnalysisModelInstanceEntryGuid": audit trail UUID
          - Tag fields and TTL counter values

        I-24 (audit trail): entityAnalysisModelInstanceEntryGuid is logged for FCA audit.
        """
        # Normalise keys to lowercase for resilience against .NET casing
        normalised = {k.lower(): v for k, v in data.items()}

        audit_guid = data.get("EntityAnalysisModelInstanceEntryGuid") or data.get(
            "entityAnalysisModelInstanceEntryGuid", ""
        )
        if audit_guid:
            logger.info("Jube audit GUID (I-24): %s", audit_guid)

        # Score: responseElevation is 0-100 (maps to Activation Rule response elevation)
        raw_score = normalised.get("responseelevation") or normalised.get("score") or 0
        try:
            score = max(0, min(100, int(raw_score)))
        except (TypeError, ValueError):
            score = 0

        # Risk classification (aligned with mock adapter thresholds)
        if score >= _SCORE_CRITICAL:
            risk = FraudRisk.CRITICAL
        elif score >= _SCORE_HIGH:
            risk = FraudRisk.HIGH
        elif score >= _SCORE_MEDIUM:
            risk = FraudRisk.MEDIUM
        else:
            risk = FraudRisk.LOW

        # Block decision: CRITICAL score OR explicit block activation rule
        block_keys = {"blocktransaction", "block", "hardblock", "reject"}
        explicit_block = any(bool(normalised.get(k)) for k in block_keys)
        block = (risk == FraudRisk.CRITICAL) or explicit_block

        # Hold decision: HIGH/MEDIUM score OR explicit hold activation rule
        hold_keys = {"holdtransaction", "hold", "holdreview", "manualreview"}
        explicit_hold = any(bool(normalised.get(k)) for k in hold_keys)
        hold = (risk in (FraudRisk.HIGH, FraudRisk.MEDIUM)) or explicit_hold

        # APP scam indicator from tags
        app_scam = self._detect_app_scam(normalised)

        # Factors: collect activated boolean rule names (human-readable audit)
        factors = [
            k
            for k, v in data.items()
            if isinstance(v, bool) and v and k not in {"EntityAnalysisModelInstanceEntryGuid"}
        ][:15]

        return FraudScoringResult(
            transaction_id=request.transaction_id,
            risk=risk,
            score=score,
            app_scam_indicator=app_scam,
            block=block,
            hold_for_review=hold,
            factors=factors,
            provider="jube",
            latency_ms=latency_ms,
        )

    def _detect_app_scam(self, normalised: dict) -> AppScamIndicator:
        """Detect PSR APP 2024 scam type from Jube activation rule tags."""
        scam_map = {
            "purchasescam": AppScamIndicator.PURCHASE_SCAM,
            "romancescam": AppScamIndicator.ROMANCE_SCAM,
            "investmentscam": AppScamIndicator.INVESTMENT_SCAM,
            "impersonationbank": AppScamIndicator.IMPERSONATION_BANK,
            "impersonationpolice": AppScamIndicator.IMPERSONATION_POLICE,
            "impersonationhmrc": AppScamIndicator.IMPERSONATION_HMRC,
            "ceofraud": AppScamIndicator.CEO_FRAUD,
            "invoiceredirect": AppScamIndicator.INVOICE_REDIRECT,
            "advancefee": AppScamIndicator.ADVANCE_FEE,
        }
        for key, indicator in scam_map.items():
            if bool(normalised.get(key)):
                return indicator
        return AppScamIndicator.NONE

    # ── Fallbacks ─────────────────────────────────────────────────────────────

    def _timeout_fallback(
        self, request: FraudScoringRequest, latency_s: float
    ) -> FraudScoringResult:
        """Conservative fallback on timeout: MEDIUM risk → HITL review."""
        return FraudScoringResult(
            transaction_id=request.transaction_id,
            risk=FraudRisk.MEDIUM,
            score=50,
            app_scam_indicator=AppScamIndicator.NONE,
            block=False,
            hold_for_review=True,
            factors=["jube_timeout"],
            provider="jube_timeout_fallback",
            latency_ms=latency_s * 1000,
        )

    def _error_fallback(
        self, request: FraudScoringRequest, latency_ms: float
    ) -> FraudScoringResult:
        """Conservative fallback on API error: MEDIUM risk → HITL review."""
        return FraudScoringResult(
            transaction_id=request.transaction_id,
            risk=FraudRisk.MEDIUM,
            score=50,
            app_scam_indicator=AppScamIndicator.NONE,
            block=False,
            hold_for_review=True,
            factors=["jube_api_error"],
            provider="jube_error_fallback",
            latency_ms=latency_ms,
        )

    # ── Health ────────────────────────────────────────────────────────────────

    def health(self) -> bool:
        """Check Jube API is reachable and credentials are valid."""
        try:
            self._get_jwt()
            return True
        except Exception as exc:
            logger.warning("Jube health check failed: %s", exc)
            return False
