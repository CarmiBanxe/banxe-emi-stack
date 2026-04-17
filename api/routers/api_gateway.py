"""
api/routers/api_gateway.py — API Gateway & Rate Limiting REST API
IL-AGW-01 | Phase 27 | banxe-emi-stack

Endpoints (prefix /v1/gateway embedded):
  POST /v1/gateway/keys                — create API key (returns raw key ONCE)
  GET  /v1/gateway/keys/{key_id}       — get key metadata (no raw key)
  GET  /v1/gateway/keys                — list keys by owner_id
  POST /v1/gateway/keys/{key_id}/revoke — revoke key (HITL I-27)
  POST /v1/gateway/check               — authenticate + rate-limit a request
  GET  /v1/gateway/keys/{key_id}/usage — request analytics and quota summary
  GET  /v1/gateway/rate-limits         — list rate limit policies
  POST /v1/gateway/ip-filter           — manage IP allowlist entry

FCA: COBS 2.1 (fair treatment), PS21/3, PSD2 RTS
Invariants: I-01 (Decimal), I-12 (SHA-256 keys), I-24 (audit), I-27 (HITL revocation)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.api_gateway.gateway_agent import GatewayAgent

router = APIRouter(tags=["api_gateway"])


# ── Dependency ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> GatewayAgent:
    return GatewayAgent()


# ── Request / Response models ─────────────────────────────────────────────────


class CreateKeyRequest(BaseModel):
    name: str
    owner_id: str
    scope: list[str]
    tier: str  # FREE | BASIC | PREMIUM | ENTERPRISE


class CheckRequestBody(BaseModel):
    raw_key: str
    method: str
    path: str
    ip_address: str


class RevokeKeyRequest(BaseModel):
    actor: str  # who is requesting revocation (for audit trail)


class IPFilterRequest(BaseModel):
    key_id: str
    cidr: str
    action: str  # ALLOW | BLOCK


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/v1/gateway/keys", status_code=201)
async def create_api_key(req: CreateKeyRequest) -> dict:
    """Create a new API key. Raw key returned ONCE — never stored (I-12).

    Returns {"raw_key": str, "key_id": str, "tier": str}.
    """
    agent = _get_agent()
    try:
        return agent.create_api_key(
            name=req.name,
            owner_id=req.owner_id,
            scope=req.scope,
            tier_str=req.tier,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/gateway/keys/{key_id}")
async def get_api_key(key_id: str) -> dict:
    """Get API key metadata by key_id. Raw key is never returned."""
    agent = _get_agent()
    api_key = agent._key_manager.get_key(key_id)  # type: ignore[attr-defined]
    if api_key is None:
        raise HTTPException(status_code=404, detail=f"Key {key_id} not found")
    return {
        "key_id": api_key.key_id,
        "name": api_key.name,
        "owner_id": api_key.owner_id,
        "scope": api_key.scope,
        "tier": api_key.tier.value,
        "status": api_key.status.value,
        "created_at": api_key.created_at.isoformat(),
    }


@router.get("/v1/gateway/keys")
async def list_api_keys(owner_id: str) -> dict:
    """List all API keys for an owner."""
    agent = _get_agent()
    keys = agent._key_manager._store.list_by_owner(owner_id)  # type: ignore[attr-defined]
    return {
        "keys": [
            {
                "key_id": k.key_id,
                "name": k.name,
                "tier": k.tier.value,
                "status": k.status.value,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ]
    }


@router.post("/v1/gateway/keys/{key_id}/revoke")
async def revoke_api_key(key_id: str, req: RevokeKeyRequest) -> dict:
    """Revoke an API key. Returns HITL_REQUIRED (I-27) — Compliance Officer must approve."""
    agent = _get_agent()
    try:
        return agent.revoke_key(key_id=key_id, actor=req.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/v1/gateway/check")
async def check_request(req: CheckRequestBody) -> dict:
    """Authenticate key, check rate limit and quota, log request.

    Returns {"allowed": bool, "key_id": str, "rate_limit": dict, "quota": dict}.
    HTTP 429 if rate-limited or quota exceeded (still returns allowed=False).
    """
    agent = _get_agent()
    result = agent.check_request(
        raw_key=req.raw_key,
        method=req.method,
        path=req.path,
        ip_address=req.ip_address,
    )
    if not result["allowed"]:
        reason = result.get("reason", "rate_limited")
        status = 401 if reason == "invalid_key" else 429 if reason != "ip_blocked" else 403
        raise HTTPException(status_code=status, detail=result)
    return result


@router.get("/v1/gateway/keys/{key_id}/usage")
async def get_key_usage(key_id: str) -> dict:
    """Return request analytics and quota summary for a key."""
    agent = _get_agent()
    return agent.get_usage_analytics(key_id=key_id)


@router.get("/v1/gateway/rate-limits")
async def list_rate_limit_policies() -> dict:
    """List all rate limit policies (one per tier)."""
    from services.api_gateway.models import UsageTier  # noqa: PLC0415

    agent = _get_agent()
    policies = []
    for tier in UsageTier:
        policy = agent._rate_limiter._policy_store.get_policy(tier)  # type: ignore[attr-defined]
        if policy:
            policies.append(
                {
                    "policy_id": policy.policy_id,
                    "tier": policy.tier.value,
                    "requests_per_second": policy.requests_per_second,
                    "requests_per_minute": policy.requests_per_minute,
                    "requests_per_hour": policy.requests_per_hour,
                    "burst_allowance": policy.burst_allowance,
                }
            )
    return {"policies": policies}


@router.post("/v1/gateway/ip-filter", status_code=201)
async def add_ip_filter(req: IPFilterRequest) -> dict:
    """Add an IP CIDR to the allowlist/blocklist for a key."""
    from services.api_gateway.models import GeoAction  # noqa: PLC0415

    agent = _get_agent()
    try:
        action = GeoAction(req.action)
        entry = agent._ip_filter.add_to_allowlist(  # type: ignore[attr-defined]
            key_id=req.key_id,
            cidr=req.cidr,
            action=action,
        )
        return {
            "entry_id": entry.entry_id,
            "key_id": entry.key_id,
            "cidr": entry.cidr,
            "action": entry.action.value,
            "created_at": entry.created_at.isoformat(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
