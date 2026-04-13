"""API Gateway — GAP-023 I-api.

Single entry-point for all Banxe EMI API requests. Provides:

  - Route validation (method + path)
  - API key authentication (X-API-Key header)
  - Rate limiting (per-key sliding window, in-memory for MVP)
  - Request/response audit logging (to AuditTrail)
  - Idempotency (Idempotency-Key header — returns cached response on replay)
  - Version routing (/v1/, /v2/, ...)

Compliance:
  PSD2 Art.18    — API access control for payment initiation
  FCA SYSC 13.7  — operational resilience: rate limiting prevents DoS
  I-21           — 5-year audit retention (via AuditTrail ClickHouse)
  GDPR Art.30    — audit log of data-processing activities

Design principles:
  - Pure Python, no HTTP server dependency (framework-agnostic)
  - Protocol-based adapters for auth and rate limiter (testable)
  - All exceptions wrapped in GatewayResponse — never raises to caller
  - AuditTrail fail-open (same as safeguarding audit_trail.py)

Usage:
    gateway = APIGateway(
        auth=InMemoryAPIKeyAuth({"sk_live_abc123": "customer-001"}),
        rate_limiter=InMemoryRateLimiter(requests_per_minute=60),
        audit=AuditTrail(clickhouse_url="...", dry_run=False),
    )
    response = gateway.handle(GatewayRequest(
        method="POST",
        path="/v1/payments",
        api_key="sk_live_abc123",
        idempotency_key="txn-uuid-001",
        body={"amount": "100.00", "currency": "GBP"},
    ))
    print(response.status_code)   # 200 or 4xx/5xx
    print(response.audit_event_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import logging
import time
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_VERSIONS = {"v1", "v2"}
DEFAULT_RATE_LIMIT = 60  # requests per minute per API key
IDEMPOTENCY_TTL_SECONDS = 86400  # 24 hours

# HTTP status codes (avoid framework dependency)
HTTP_200 = 200
HTTP_400 = 400
HTTP_401 = 401
HTTP_403 = 403
HTTP_404 = 404
HTTP_409 = 409  # Conflict (idempotency replay with different body)
HTTP_422 = 422
HTTP_429 = 429  # Too Many Requests
HTTP_500 = 500


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class GatewayRequest:
    """Inbound API request after HTTP framework parsing.

    Attributes:
        method:          HTTP method (GET, POST, PUT, DELETE, PATCH).
        path:            URL path including version prefix (e.g. /v1/payments).
        api_key:         Value of X-API-Key header (empty string if absent).
        body:            Parsed JSON body as dict (empty dict if no body).
        headers:         All request headers as dict.
        idempotency_key: Value of Idempotency-Key header (empty = no idempotency).
        client_ip:       Client IP address for rate limiting and audit.
        request_id:      Framework-assigned request ID (UUID generated if absent).
    """

    method: str
    path: str
    api_key: str = ""
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    idempotency_key: str = ""
    client_ip: str = ""
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class GatewayResponse:
    """Outbound API response.

    Attributes:
        status_code:     HTTP status code.
        body:            Response body as dict (will be JSON-serialised by framework).
        request_id:      Echoed from GatewayRequest.request_id.
        audit_event_id:  ID of the AuditEvent written for this request.
        from_cache:      True if response was served from idempotency cache.
    """

    status_code: int
    body: dict[str, Any]
    request_id: str = ""
    audit_event_id: str = ""
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass
class RouteDefinition:
    """One registered route.

    Attributes:
        method:       HTTP method (uppercase).
        path_prefix:  URL path prefix the route matches (e.g. "/v1/payments").
        handler_name: Human-readable name for audit logging.
        versions:     Supported API versions (empty = all).
        requires_auth: If False, auth check is skipped (e.g. /health endpoint).
    """

    method: str
    path_prefix: str
    handler_name: str
    versions: set[str] = field(default_factory=set)
    requires_auth: bool = True


# ── Ports (Protocol) ───────────────────────────────────────────────────────────


@runtime_checkable
class APIKeyAuthPort(Protocol):
    """Validate an API key and return the associated customer/entity ID."""

    def authenticate(self, api_key: str) -> str | None:
        """Return entity_id if valid, None if invalid/unknown."""
        ...


@runtime_checkable
class RateLimiterPort(Protocol):
    """Sliding-window rate limiter per API key."""

    def is_allowed(self, api_key: str) -> bool:
        """Return True if request is within limits, False if throttled."""
        ...

    def record(self, api_key: str) -> None:
        """Record a request for rate limiting accounting."""
        ...


@runtime_checkable
class IdempotencyStorePort(Protocol):
    """Store and retrieve idempotency-key → response mappings."""

    def get(self, key: str, body_hash: str) -> GatewayResponse | None:
        """Return cached response if exists and body_hash matches, else None."""
        ...

    def put(self, key: str, body_hash: str, response: GatewayResponse) -> None:
        """Store response under idempotency key."""
        ...


@runtime_checkable
class AuditTrailPort(Protocol):
    """Write audit events — same interface as safeguarding AuditTrail."""

    def log(self, event: Any) -> str:
        """Log event; return event_id. Never raises."""
        ...


# ── In-memory adapters ─────────────────────────────────────────────────────────


class InMemoryAPIKeyAuth:
    """Simple dict-based API key store. For tests and sandbox."""

    def __init__(self, keys: dict[str, str] | None = None) -> None:
        # api_key → entity_id
        self._keys: dict[str, str] = keys or {}

    def authenticate(self, api_key: str) -> str | None:
        return self._keys.get(api_key)

    def add_key(self, api_key: str, entity_id: str) -> None:
        self._keys[api_key] = entity_id

    def revoke_key(self, api_key: str) -> None:
        self._keys.pop(api_key, None)


class InMemoryRateLimiter:
    """Token-bucket rate limiter backed by an in-memory dict.

    Uses a sliding window: keeps timestamps of recent requests per key.
    """

    def __init__(self, requests_per_minute: int = DEFAULT_RATE_LIMIT) -> None:
        self._rpm = requests_per_minute
        self._window: dict[str, list[float]] = {}

    def is_allowed(self, api_key: str) -> bool:
        now = time.monotonic()
        window_start = now - 60.0
        history = [t for t in self._window.get(api_key, []) if t >= window_start]
        self._window[api_key] = history
        return len(history) < self._rpm

    def record(self, api_key: str) -> None:
        now = time.monotonic()
        if api_key not in self._window:
            self._window[api_key] = []
        self._window[api_key].append(now)


class InMemoryIdempotencyStore:
    """In-memory idempotency store with TTL. For tests and sandbox."""

    def __init__(self, ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[str, GatewayResponse, float]] = {}
        # key → (body_hash, response, stored_at)

    def get(self, key: str, body_hash: str) -> GatewayResponse | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        stored_hash, response, stored_at = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._store[key]
            return None
        if stored_hash != body_hash:
            # Same idempotency key, different body → 409 Conflict
            return GatewayResponse(
                status_code=HTTP_409,
                body={"error": "Idempotency key reused with different request body"},
                from_cache=True,
            )
        response.from_cache = True
        return response

    def put(self, key: str, body_hash: str, response: GatewayResponse) -> None:
        self._store[key] = (body_hash, response, time.monotonic())


class NullAuditTrail:
    """No-op audit trail. For tests that don't need audit output."""

    def log(self, event: Any) -> str:
        return str(uuid4())


# ── Gateway ────────────────────────────────────────────────────────────────────


class APIGateway:
    """Framework-agnostic API gateway with auth, rate limiting, and audit.

    Args:
        auth:          APIKeyAuthPort implementation.
        rate_limiter:  RateLimiterPort implementation.
        idempotency:   IdempotencyStorePort implementation (None = disabled).
        audit:         AuditTrailPort implementation.
        routes:        Registered routes. If empty, all paths pass route check.
    """

    def __init__(
        self,
        auth: APIKeyAuthPort,
        rate_limiter: RateLimiterPort,
        idempotency: IdempotencyStorePort | None = None,
        audit: AuditTrailPort | None = None,
        routes: list[RouteDefinition] | None = None,
    ) -> None:
        self._auth = auth
        self._rate_limiter = rate_limiter
        self._idempotency = idempotency or InMemoryIdempotencyStore()
        self._audit = audit or NullAuditTrail()
        self._routes = routes or []

    def register_route(self, route: RouteDefinition) -> None:
        """Register a new route at runtime."""
        self._routes.append(route)

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        """Process one API request through the full gateway pipeline.

        Pipeline:
          1. Version extraction
          2. Route validation
          3. Auth check
          4. Rate limit check
          5. Idempotency lookup
          6. (Placeholder) downstream dispatch
          7. Idempotency store
          8. Audit log
        """
        audit_event_id = ""
        try:
            response = self._pipeline(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("APIGateway FATAL for request %s: %s", request.request_id, exc)
            response = GatewayResponse(
                status_code=HTTP_500,
                body={"error": "Internal gateway error", "request_id": request.request_id},
                request_id=request.request_id,
            )

        # Always audit log (fail-open)
        try:
            audit_event_id = self._write_audit(request, response)
        except Exception as exc:  # noqa: BLE001
            logger.error("APIGateway: audit log failed for %s: %s", request.request_id, exc)

        response.audit_event_id = audit_event_id
        return response

    def _pipeline(self, request: GatewayRequest) -> GatewayResponse:
        """Run request through all gateway stages. Raises on unrecoverable errors."""

        # ── Stage 1: Extract API version ─────────────────────────────────────
        version = self._extract_version(request.path)

        # ── Stage 2: Route validation ─────────────────────────────────────────
        if self._routes:
            route = self._match_route(request.method, request.path)
            if route is None:
                return GatewayResponse(
                    status_code=HTTP_404,
                    body={"error": f"Route not found: {request.method} {request.path}"},
                    request_id=request.request_id,
                )
            if version and route.versions and version not in route.versions:
                return GatewayResponse(
                    status_code=HTTP_400,
                    body={"error": f"API version '{version}' not supported for this route"},
                    request_id=request.request_id,
                )
            requires_auth = route.requires_auth
        else:
            requires_auth = True  # Default: auth required when no routes registered

        # ── Stage 3: Auth ─────────────────────────────────────────────────────
        entity_id: str | None = None
        if requires_auth:
            if not request.api_key:
                return GatewayResponse(
                    status_code=HTTP_401,
                    body={"error": "Missing X-API-Key header"},
                    request_id=request.request_id,
                )
            entity_id = self._auth.authenticate(request.api_key)
            if entity_id is None:
                return GatewayResponse(
                    status_code=HTTP_403,
                    body={"error": "Invalid or revoked API key"},
                    request_id=request.request_id,
                )

        # ── Stage 4: Rate limiting ────────────────────────────────────────────
        rate_key = request.api_key or request.client_ip or "anonymous"
        if not self._rate_limiter.is_allowed(rate_key):
            return GatewayResponse(
                status_code=HTTP_429,
                body={"error": "Rate limit exceeded. Retry after 60 seconds."},
                request_id=request.request_id,
            )
        self._rate_limiter.record(rate_key)

        # ── Stage 5: Idempotency lookup ───────────────────────────────────────
        body_hash = self._hash_body(request.body)
        if request.idempotency_key:
            cached = self._idempotency.get(request.idempotency_key, body_hash)
            if cached is not None:
                cached.request_id = request.request_id
                return cached

        # ── Stage 6: Downstream dispatch (MVP: passthrough 200) ───────────────
        response = GatewayResponse(
            status_code=HTTP_200,
            body={
                "status": "accepted",
                "request_id": request.request_id,
                "api_version": version or "v1",
            },
            request_id=request.request_id,
        )

        # ── Stage 7: Store idempotency ─────────────────────────────────────────
        if request.idempotency_key and response.ok:
            self._idempotency.put(request.idempotency_key, body_hash, response)

        return response

    def _extract_version(self, path: str) -> str | None:
        """Extract /vN/ prefix from path. Returns None if not a versioned path."""
        parts = path.strip("/").split("/")
        if parts and parts[0] in SUPPORTED_VERSIONS:
            return parts[0]
        return None

    def _match_route(self, method: str, path: str) -> RouteDefinition | None:
        """Return the first route that matches method + path prefix."""
        for route in self._routes:
            if route.method.upper() != method.upper():
                continue
            if path.startswith(route.path_prefix):
                return route
        return None

    @staticmethod
    def _hash_body(body: dict[str, Any]) -> str:
        """Stable SHA-256 hash of body dict for idempotency comparison."""
        import json

        raw = json.dumps(body, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _write_audit(self, request: GatewayRequest, response: GatewayResponse) -> str:
        """Write audit event. Returns event_id. Never raises (fail-open)."""
        try:
            # Build a minimal audit event dict (compatible with AuditEvent dataclass)
            event = _AuditEventProxy(
                event_type="API_REQUEST",
                entity_id=request.request_id,
                actor=request.api_key or "anonymous",
                payload={
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "idempotency_key": request.idempotency_key or None,
                    "from_cache": response.from_cache,
                    "client_ip": request.client_ip or None,
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                },
                severity="INFO" if response.ok else "WARNING",
            )
            return self._audit.log(event)
        except Exception as exc:  # noqa: BLE001
            logger.error("APIGateway._write_audit failed: %s", exc)
            return ""


class _AuditEventProxy:
    """Minimal duck-type proxy compatible with safeguarding AuditEvent."""

    def __init__(
        self,
        event_type: str,
        entity_id: str,
        actor: str,
        payload: dict[str, Any],
        severity: str,
    ) -> None:
        from uuid import uuid4

        self.event_id = str(uuid4())
        self.event_type = event_type
        self.entity_id = entity_id
        self.actor = actor
        self.payload = payload
        self.severity = severity
        self.occurred_at = datetime.now(UTC)

    def payload_json(self) -> str:
        import json

        return json.dumps(self.payload, default=str)
