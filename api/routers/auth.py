"""
api/routers/auth.py — Authentication endpoint
IL-046 | banxe-emi-stack

POST /v1/auth/login
  Body: { email, pin }
  Returns: { token, expires_at }

MVP logic:
  - Look up customer by email in InMemoryCustomerService
  - Validate PIN format (6 digits — in production, compare against stored hash)
  - Issue HS256 JWT signed with AUTH_SECRET_KEY (from env)
  - Token lifetime: AUTH_TOKEN_TTL_HOURS (default 24 h)

Security notes:
  - In production: replace PIN equality check with bcrypt/argon2 hash comparison
  - In production: add rate-limiting / account lock after N failed attempts (PSD2 SCA)
  - AUTH_SECRET_KEY must be at least 32 random bytes
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_customer_service
from api.models.auth import LoginRequest, LoginResponse
from services.customer.customer_service import InMemoryCustomerService

logger = logging.getLogger("banxe.auth")

router = APIRouter(tags=["Auth"])

# ── Config ────────────────────────────────────────────────────────────────────

_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-change-in-prod")
_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "24"))
_ALGORITHM = "HS256"

# MVP dev PIN — in production each customer has a hashed PIN stored securely
_DEV_PIN = os.environ.get("AUTH_DEV_PIN", "123456")


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
def login(
    body: LoginRequest,
    svc: InMemoryCustomerService = Depends(get_customer_service),
) -> LoginResponse:
    """
    Issue a JWT for the customer identified by *email*.

    MVP: any registered email + the configured PIN grants access.
    The token carries ``sub`` (customer_id) and ``email`` claims.
    """
    # 1. Look up customer by email
    customers = svc.list_customers()
    customer = next(
        (c for c in customers if c.metadata.get("email") == body.email),
        None,
    )
    if customer is None:
        # Return 401 (not 404) to avoid email enumeration.
        # I-09: do NOT log email — GDPR PII
        logger.warning("auth.login email_not_found")
        raise HTTPException(status_code=401, detail="Invalid email or PIN")

    # 2. Validate PIN (MVP: compare against _DEV_PIN; production: bcrypt verify)
    if body.pin != _DEV_PIN:
        logger.warning("auth.login invalid_pin customer_id=%s", customer.customer_id)
        raise HTTPException(status_code=401, detail="Invalid email or PIN")

    # 3. Issue JWT
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(hours=_TTL_HOURS)

    payload = {
        "sub": customer.customer_id,
        "email": body.email,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)

    logger.info("auth.login success customer_id=%s", customer.customer_id)
    return LoginResponse(token=token, expires_at=expires_at)
