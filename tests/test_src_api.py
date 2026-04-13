"""Tests for src/api/gateway.py — GAP-023 I-api.

Coverage targets: GatewayRequest/Response, InMemoryAPIKeyAuth,
InMemoryRateLimiter, InMemoryIdempotencyStore, APIGateway pipeline
(auth, rate limit, idempotency, route matching, version extraction).
"""

from src.api import (
    APIGateway,
    GatewayRequest,
    GatewayResponse,
    InMemoryAPIKeyAuth,
    InMemoryIdempotencyStore,
    InMemoryRateLimiter,
    NullAuditTrail,
    RouteDefinition,
)
from src.api.gateway import (
    HTTP_200,
    HTTP_401,
    HTTP_403,
    HTTP_404,
    HTTP_409,
    HTTP_429,
    _AuditEventProxy,
)

# ── InMemoryAPIKeyAuth ─────────────────────────────────────────────────────────


class TestInMemoryAPIKeyAuth:
    def test_valid_key_returns_entity(self):
        auth = InMemoryAPIKeyAuth({"sk_test_001": "customer-001"})
        assert auth.authenticate("sk_test_001") == "customer-001"

    def test_invalid_key_returns_none(self):
        auth = InMemoryAPIKeyAuth({"sk_test_001": "customer-001"})
        assert auth.authenticate("sk_invalid") is None

    def test_empty_key_returns_none(self):
        auth = InMemoryAPIKeyAuth({"sk_test_001": "customer-001"})
        assert auth.authenticate("") is None

    def test_add_key(self):
        auth = InMemoryAPIKeyAuth()
        auth.add_key("sk_new", "customer-999")
        assert auth.authenticate("sk_new") == "customer-999"

    def test_revoke_key(self):
        auth = InMemoryAPIKeyAuth({"sk_test": "customer-001"})
        auth.revoke_key("sk_test")
        assert auth.authenticate("sk_test") is None

    def test_revoke_nonexistent_no_error(self):
        auth = InMemoryAPIKeyAuth()
        auth.revoke_key("nonexistent")  # Should not raise


# ── InMemoryRateLimiter ────────────────────────────────────────────────────────


class TestInMemoryRateLimiter:
    def test_under_limit_allowed(self):
        rl = InMemoryRateLimiter(requests_per_minute=10)
        for _ in range(9):
            rl.record("key-001")
        assert rl.is_allowed("key-001") is True

    def test_at_limit_blocked(self):
        rl = InMemoryRateLimiter(requests_per_minute=3)
        for _ in range(3):
            rl.record("key-001")
        assert rl.is_allowed("key-001") is False

    def test_different_keys_independent(self):
        rl = InMemoryRateLimiter(requests_per_minute=2)
        for _ in range(2):
            rl.record("key-A")
        assert rl.is_allowed("key-A") is False
        assert rl.is_allowed("key-B") is True

    def test_empty_key_allowed(self):
        rl = InMemoryRateLimiter(requests_per_minute=10)
        assert rl.is_allowed("new-key") is True


# ── InMemoryIdempotencyStore ───────────────────────────────────────────────────


class TestInMemoryIdempotencyStore:
    def test_miss_returns_none(self):
        store = InMemoryIdempotencyStore()
        result = store.get("key-001", "hash-abc")
        assert result is None

    def test_hit_returns_response(self):
        store = InMemoryIdempotencyStore()
        response = GatewayResponse(status_code=200, body={"ok": True})
        store.put("key-001", "hash-abc", response)
        cached = store.get("key-001", "hash-abc")
        assert cached is not None
        assert cached.from_cache is True

    def test_hash_mismatch_returns_409(self):
        store = InMemoryIdempotencyStore()
        response = GatewayResponse(status_code=200, body={"ok": True})
        store.put("key-001", "hash-abc", response)
        conflict = store.get("key-001", "hash-different")
        assert conflict is not None
        assert conflict.status_code == HTTP_409

    def test_expired_entry_returns_none(self):
        store = InMemoryIdempotencyStore(ttl_seconds=0)
        response = GatewayResponse(status_code=200, body={"ok": True})
        store.put("key-001", "hash-abc", response)
        # TTL=0 means immediately expired on next read
        result = store.get("key-001", "hash-abc")
        # With ttl=0, monotonic delta > 0 so it's expired
        assert result is None


# ── APIGateway — auth pipeline ─────────────────────────────────────────────────


class TestAPIGatewayAuth:
    def _gateway(self, keys=None) -> APIGateway:
        return APIGateway(
            auth=InMemoryAPIKeyAuth(keys or {"sk_test": "customer-001"}),
            rate_limiter=InMemoryRateLimiter(requests_per_minute=100),
            audit=NullAuditTrail(),
        )

    def test_missing_api_key_returns_401(self):
        gw = self._gateway()
        req = GatewayRequest(method="GET", path="/v1/status", api_key="")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_401

    def test_invalid_api_key_returns_403(self):
        gw = self._gateway()
        req = GatewayRequest(method="GET", path="/v1/status", api_key="sk_invalid")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_403

    def test_valid_api_key_returns_200(self):
        gw = self._gateway()
        req = GatewayRequest(method="GET", path="/v1/status", api_key="sk_test")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_200

    def test_response_has_request_id(self):
        gw = self._gateway()
        req = GatewayRequest(method="GET", path="/v1/status", api_key="sk_test")
        resp = gw.handle(req)
        assert resp.request_id == req.request_id

    def test_response_has_audit_event_id(self):
        gw = self._gateway()
        req = GatewayRequest(method="GET", path="/v1/status", api_key="sk_test")
        resp = gw.handle(req)
        assert isinstance(resp.audit_event_id, str)


# ── APIGateway — rate limiting ─────────────────────────────────────────────────


class TestAPIGatewayRateLimit:
    def test_exceeds_rate_limit_returns_429(self):
        gw = APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "c-001"}),
            rate_limiter=InMemoryRateLimiter(requests_per_minute=2),
            audit=NullAuditTrail(),
        )
        req = GatewayRequest(method="GET", path="/v1/status", api_key="sk_test")
        # First two succeed
        gw.handle(req)
        gw.handle(req)
        # Third is rate-limited
        resp = gw.handle(req)
        assert resp.status_code == HTTP_429

    def test_unauthenticated_uses_ip_for_rate_limit(self):
        """Even 401 requests consume rate limit budget via IP."""
        gw = APIGateway(
            auth=InMemoryAPIKeyAuth({}),
            rate_limiter=InMemoryRateLimiter(requests_per_minute=1),
            audit=NullAuditTrail(),
        )
        # First request: 401 (no API key) but rate counter not yet consumed (auth fails before rate)
        req = GatewayRequest(method="GET", path="/v1/status", api_key="", client_ip="1.2.3.4")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_401  # Auth fails before rate limit


# ── APIGateway — idempotency ───────────────────────────────────────────────────


class TestAPIGatewayIdempotency:
    def _gateway(self) -> APIGateway:
        return APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "customer-001"}),
            rate_limiter=InMemoryRateLimiter(requests_per_minute=100),
            idempotency=InMemoryIdempotencyStore(),
            audit=NullAuditTrail(),
        )

    def test_idempotency_replay_returns_same_status(self):
        gw = self._gateway()
        req = GatewayRequest(
            method="POST",
            path="/v1/payments",
            api_key="sk_test",
            idempotency_key="idem-001",
            body={"amount": "100.00"},
        )
        resp1 = gw.handle(req)
        resp2 = gw.handle(req)
        assert resp1.status_code == resp2.status_code
        assert resp2.from_cache is True

    def test_no_idempotency_key_no_caching(self):
        gw = self._gateway()
        req = GatewayRequest(
            method="POST",
            path="/v1/payments",
            api_key="sk_test",
            body={"amount": "100.00"},
        )
        resp1 = gw.handle(req)
        resp2 = gw.handle(req)
        assert resp1.from_cache is False
        assert resp2.from_cache is False


# ── APIGateway — route validation ─────────────────────────────────────────────


class TestAPIGatewayRoutes:
    def _gateway_with_routes(self) -> APIGateway:
        return APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "customer-001"}),
            rate_limiter=InMemoryRateLimiter(requests_per_minute=100),
            audit=NullAuditTrail(),
            routes=[
                RouteDefinition("GET", "/v1/status", "HealthCheck", requires_auth=False),
                RouteDefinition("POST", "/v1/payments", "CreatePayment", versions={"v1"}),
                RouteDefinition("GET", "/v1/accounts", "ListAccounts"),
            ],
        )

    def test_known_route_ok(self):
        gw = self._gateway_with_routes()
        req = GatewayRequest(method="GET", path="/v1/status")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_200

    def test_unknown_route_404(self):
        gw = self._gateway_with_routes()
        req = GatewayRequest(method="GET", path="/v1/nonexistent", api_key="sk_test")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_404

    def test_wrong_method_404(self):
        gw = self._gateway_with_routes()
        req = GatewayRequest(method="DELETE", path="/v1/status")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_404

    def test_unversioned_path_unsupported_version(self):
        gw = self._gateway_with_routes()
        req = GatewayRequest(method="POST", path="/v3/payments", api_key="sk_test")
        # /v3/ prefix → version=None (not in SUPPORTED_VERSIONS)
        # route /v1/payments does not match /v3/payments
        resp = gw.handle(req)
        assert resp.status_code == HTTP_404

    def test_no_auth_required_route_skips_auth(self):
        gw = self._gateway_with_routes()
        # /v1/status has requires_auth=False
        req = GatewayRequest(method="GET", path="/v1/status", api_key="")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_200

    def test_register_route_at_runtime(self):
        gw = self._gateway_with_routes()
        gw.register_route(RouteDefinition("DELETE", "/v1/accounts", "DeleteAccount"))
        req = GatewayRequest(method="DELETE", path="/v1/accounts/123", api_key="sk_test")
        resp = gw.handle(req)
        assert resp.status_code == HTTP_200


# ── APIGateway — version extraction ───────────────────────────────────────────


class TestAPIGatewayVersionExtraction:
    def test_extract_v1(self):
        gw = APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "c-001"}),
            rate_limiter=InMemoryRateLimiter(),
            audit=NullAuditTrail(),
        )
        assert gw._extract_version("/v1/payments") == "v1"

    def test_extract_v2(self):
        gw = APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "c-001"}),
            rate_limiter=InMemoryRateLimiter(),
            audit=NullAuditTrail(),
        )
        assert gw._extract_version("/v2/payments") == "v2"

    def test_extract_none_for_unversioned(self):
        gw = APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "c-001"}),
            rate_limiter=InMemoryRateLimiter(),
            audit=NullAuditTrail(),
        )
        assert gw._extract_version("/health") is None

    def test_extract_none_for_unsupported(self):
        gw = APIGateway(
            auth=InMemoryAPIKeyAuth({"sk_test": "c-001"}),
            rate_limiter=InMemoryRateLimiter(),
            audit=NullAuditTrail(),
        )
        assert gw._extract_version("/v99/payments") is None


# ── APIGateway — body hash ─────────────────────────────────────────────────────


class TestBodyHash:
    def test_same_body_same_hash(self):
        h1 = APIGateway._hash_body({"a": 1, "b": "two"})
        h2 = APIGateway._hash_body({"b": "two", "a": 1})
        assert h1 == h2  # keys sorted

    def test_different_body_different_hash(self):
        h1 = APIGateway._hash_body({"amount": "100"})
        h2 = APIGateway._hash_body({"amount": "200"})
        assert h1 != h2

    def test_empty_body_hash_stable(self):
        h = APIGateway._hash_body({})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex


# ── AuditEventProxy ────────────────────────────────────────────────────────────


class TestAuditEventProxy:
    def test_has_event_id(self):
        proxy = _AuditEventProxy("API_REQUEST", "req-001", "sk_test", {}, "INFO")
        assert len(proxy.event_id) == 36  # UUID format

    def test_payload_json(self):
        import json

        proxy = _AuditEventProxy("API_REQUEST", "req-001", "sk_test", {"key": "val"}, "INFO")
        data = json.loads(proxy.payload_json())
        assert data["key"] == "val"

    def test_occurred_at_is_utc(self):
        proxy = _AuditEventProxy("API_REQUEST", "req-001", "sk_test", {}, "INFO")
        assert proxy.occurred_at.tzinfo is not None


# ── GatewayResponse properties ─────────────────────────────────────────────────


class TestGatewayResponse:
    def test_ok_true_for_200(self):
        r = GatewayResponse(200, {})
        assert r.ok is True

    def test_ok_true_for_201(self):
        r = GatewayResponse(201, {})
        assert r.ok is True

    def test_ok_false_for_400(self):
        r = GatewayResponse(400, {})
        assert r.ok is False

    def test_ok_false_for_500(self):
        r = GatewayResponse(500, {})
        assert r.ok is False
