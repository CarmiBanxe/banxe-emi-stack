"""
api/routers/auth.py — Authentication endpoint
IL-046 | banxe-emi-stack

POST /v1/auth/login
  Body: { email, pin }
  Returns: { token, expires_at }

Lookup order:
  1. PostgreSQL/SQLite customers table (persistent)
  2. Fallback: InMemoryCustomerService (sandbox / test)

Security notes:
  - In production: replace PIN equality check with bcrypt/argon2 hash
  - In production: add rate-limiting / account lock (PSD2 SCA)
  - AUTH_SECRET_KEY must be at least 32 random bytes
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AuthSession, Customer
from api.deps import get_customer_service, get_db
from api.models.auth import LoginRequest, LoginResponse
from services.customer.customer_service import InMemoryCustomerService

logger = logging.getLogger("banxe.auth")

router = APIRouter(tags=["Auth"])

# ── Config ────────────────────────────────────────────────────────────────────

_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-change-in-prod")
_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "24"))
_ALGORITHM = "HS256"
_DEV_PIN = os.environ.get("AUTH_DEV_PIN", "123456")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_customer_by_email_db(db: AsyncSession, email: str) -> Customer | None:
    """Look up a customer by email in the persistent DB."""
    result = await db.execute(select(Customer).where(Customer.email == email))
    return result.scalar_one_or_none()


def _get_customer_by_email_memory(
    svc: InMemoryCustomerService, email: str
) -> tuple[str, str] | None:
    """
    Look up customer in InMemoryCustomerService.
    Returns (customer_id, email) or None.
    """
    for c in svc.list_customers():
        if c.metadata.get("email") == email:
            return c.customer_id, email
    return None


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Authenticate and obtain a JWT Bearer token",
    responses={
        401: {"description": "Invalid credentials"},
        422: {"description": "Validation error (e.g. PIN not 6 digits)"},
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    svc: InMemoryCustomerService = Depends(get_customer_service),
) -> LoginResponse:
    """
    Issue a JWT for the customer identified by *email*.

    Lookup strategy:
      1. Persistent DB (PostgreSQL / SQLite) — populated on customer creation
      2. InMemoryCustomerService fallback — for sandbox / test environments

    MVP PIN validation: compares against AUTH_DEV_PIN env var.
    Production: store per-customer bcrypt hash in DB and verify here.
    """
    # 1. Find customer — DB first, then InMemory fallback
    customer_id: str | None = None
    customer_email: str = body.email

    try:
        db_customer = await _get_customer_by_email_db(db, body.email)
        if db_customer is not None:
            customer_id = db_customer.customer_id
    except Exception:
        logger.warning("auth.login db_lookup_failed — falling back to InMemory")

    if customer_id is None:
        # Fallback: InMemory (sandbox / test)
        memory_result = _get_customer_by_email_memory(svc, body.email)
        if memory_result is not None:
            customer_id, customer_email = memory_result

    if customer_id is None:
        # I-09: do NOT log email — GDPR PII
        logger.warning("auth.login email_not_found")
        raise HTTPException(status_code=401, detail="Invalid email or PIN")

    # 2. Validate PIN
    if body.pin != _DEV_PIN:
        logger.warning("auth.login invalid_pin customer_id=%s", customer_id)
        raise HTTPException(status_code=401, detail="Invalid email or PIN")

    # 3. Issue JWT
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(hours=_TTL_HOURS)

    payload = {
        "sub": customer_id,
        "email": customer_email,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)

    # 4. Persist auth session (best-effort — don't fail login if DB is down)
    try:
        session = AuthSession(
            session_id=str(uuid.uuid4()),
            customer_id=customer_id,
            token_prefix=token[:16],
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(session)
        await db.flush()
    except Exception:
        logger.warning("auth.login session_persist_failed customer_id=%s", customer_id)

    logger.info("auth.login success customer_id=%s", customer_id)
    return LoginResponse(token=token, expires_at=expires_at)
