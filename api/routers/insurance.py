"""
api/routers/insurance.py — Insurance Integration REST API
IL-INS-01 | Phase 26 | banxe-emi-stack

Endpoints (prefix /v1/insurance embedded):
  GET  /v1/insurance/products              — list all products (or filter by coverage_type)
  GET  /v1/insurance/products/{product_id} — get product details
  POST /v1/insurance/quote                 — calculate premium and create quote
  POST /v1/insurance/policies/{policy_id}/bind — bind + activate a quoted policy
  GET  /v1/insurance/policies/{policy_id}  — get policy details
  GET  /v1/insurance/policies              — list policies by customer_id
  POST /v1/insurance/claims/file           — file a new claim
  POST /v1/insurance/claims/{claim_id}/assess — move claim to UNDER_ASSESSMENT

FCA: ICOBS, IDD, FCA PS21/3 (fair value)
Invariants: I-01 (Decimal), I-05 (amounts as strings), I-27 (HITL for claim payouts >£1000)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.insurance.insurance_agent import InsuranceAgent

router = APIRouter(tags=["insurance"])


# ── Dependency ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> InsuranceAgent:
    return InsuranceAgent()


# ── Request / Response models ─────────────────────────────────────────────────


class QuoteRequest(BaseModel):
    customer_id: str
    product_id: str
    coverage_amount: str  # DecimalString (I-05)
    term_days: int


class BindRequest(BaseModel):
    pass  # policy_id is in the path


class ClaimFileRequest(BaseModel):
    policy_id: str
    customer_id: str
    claimed_amount: str  # DecimalString (I-05)
    description: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/v1/insurance/products")
async def list_products(coverage_type: str = "") -> dict:
    """List all insurance products, optionally filtered by coverage_type."""
    agent = _get_agent()
    return agent.list_products(coverage_type=coverage_type)


@router.get("/v1/insurance/products/{product_id}")
async def get_product(product_id: str) -> dict:
    """Get insurance product details by ID."""
    agent = _get_agent()
    result = agent.list_products()
    products = result.get("products", [])
    for p in products:
        if p["product_id"] == product_id:
            return p
    raise HTTPException(status_code=404, detail=f"Product {product_id} not found")


@router.post("/v1/insurance/quote", status_code=201)
async def quote_policy(req: QuoteRequest) -> dict:
    """Calculate premium and create a QUOTED policy.

    Returns policy with status=QUOTED. Use /bind to activate.
    All monetary amounts returned as strings (I-05).
    """
    try:
        Decimal(req.coverage_amount)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid coverage_amount: {req.coverage_amount}"
        ) from exc

    agent = _get_agent()
    try:
        return agent.get_quote(
            customer_id=req.customer_id,
            product_id=req.product_id,
            coverage_amount_str=req.coverage_amount,
            term_days=req.term_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/v1/insurance/policies/{policy_id}/bind")
async def bind_policy(policy_id: str) -> dict:
    """Bind (QUOTED→BOUND→ACTIVE) a policy. Returns activated policy."""
    agent = _get_agent()
    try:
        return agent.bind_policy(policy_id=policy_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/insurance/policies")
async def list_policies(customer_id: str) -> dict:
    """List all policies for a customer (customer_id required as query param)."""
    agent = _get_agent()
    # Access policy manager directly via catalog listing - return all matching customer
    policies = [
        p
        for p in agent._policy_manager._policy_store.list_by_customer(customer_id)  # type: ignore[attr-defined]
    ]
    from services.insurance.insurance_agent import _policy_to_dict  # noqa: PLC0415

    return {"policies": [_policy_to_dict(p) for p in policies]}


@router.get("/v1/insurance/policies/{policy_id}")
async def get_policy(policy_id: str) -> dict:
    """Get policy details by policy_id."""
    agent = _get_agent()
    policy = agent._policy_manager.get_policy(policy_id)  # type: ignore[attr-defined]
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    from services.insurance.insurance_agent import _policy_to_dict  # noqa: PLC0415

    return _policy_to_dict(policy)


@router.post("/v1/insurance/claims/file", status_code=201)
async def file_claim(req: ClaimFileRequest) -> dict:
    """File a claim against an active policy.

    Returns claim status. Claims >£1000 return {"status": "HITL_REQUIRED"} (I-27).
    """
    try:
        Decimal(req.claimed_amount)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid claimed_amount: {req.claimed_amount}"
        ) from exc

    agent = _get_agent()
    try:
        return agent.file_claim(
            policy_id=req.policy_id,
            customer_id=req.customer_id,
            claimed_amount_str=req.claimed_amount,
            description=req.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v1/insurance/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    """Get claim details by claim_id."""
    agent = _get_agent()
    claim = agent._claims_processor._claim_store.get(claim_id)  # type: ignore[attr-defined]
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    from services.insurance.insurance_agent import _claim_to_dict  # noqa: PLC0415

    return _claim_to_dict(claim)


@router.get("/v1/insurance/policies/{policy_id}/claims")
async def list_claims_for_policy(policy_id: str) -> dict:
    """List all claims filed against a policy."""
    agent = _get_agent()
    claims = agent._claims_processor._claim_store.list_by_policy(policy_id)  # type: ignore[attr-defined]
    from services.insurance.insurance_agent import _claim_to_dict  # noqa: PLC0415

    return {"claims": [_claim_to_dict(c) for c in claims]}


@router.post("/v1/insurance/claims/{claim_id}/assess")
async def assess_claim(claim_id: str) -> dict:
    """Move a FILED claim to UNDER_ASSESSMENT stage."""
    agent = _get_agent()
    try:
        claim = agent._claims_processor.assess_claim(claim_id)  # type: ignore[attr-defined]
        from services.insurance.insurance_agent import _claim_to_dict  # noqa: PLC0415

        return _claim_to_dict(claim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
