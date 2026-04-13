"""Banxe EMI — API Gateway (GAP-023 I-api).

Framework-agnostic API gateway: auth, rate limiting, idempotency, audit.

Compliance:
  - PSD2 Art.18    — API access control
  - FCA SYSC 13.7  — operational resilience
  - I-21           — 5-year audit retention
"""

from .gateway import (
    APIGateway,
    APIKeyAuthPort,
    GatewayRequest,
    GatewayResponse,
    IdempotencyStorePort,
    InMemoryAPIKeyAuth,
    InMemoryIdempotencyStore,
    InMemoryRateLimiter,
    NullAuditTrail,
    RateLimiterPort,
    RouteDefinition,
)

__all__ = [
    "GatewayRequest",
    "GatewayResponse",
    "RouteDefinition",
    "APIKeyAuthPort",
    "RateLimiterPort",
    "IdempotencyStorePort",
    "APIGateway",
    "InMemoryAPIKeyAuth",
    "InMemoryRateLimiter",
    "InMemoryIdempotencyStore",
    "NullAuditTrail",
]
