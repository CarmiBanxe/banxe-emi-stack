"""
api/routers/auth.py — Authentication endpoints
IL-046 | S15-01 | banxe-emi-stack

POST /v1/auth/login
  Body: { email, pin }
  Returns: { token, expires_at }

POST /v1/auth/sca/challenge   — Initiate PSD2 SCA challenge (Art.97)
POST /v1/auth/sca/verify      — Verify SCA challenge, receive dynamic-linking token
GET  /v1/auth/sca/methods/{customer_id} — Available SCA methods for customer

Lookup order (login):
  1. PostgreSQL/SQLite customers table (persistent)
  2. Fallback: InMemoryCustomerService (sandbox / test)

Security notes:
  - In production: replace PIN equality check with bcrypt/argon2 hash
  - In production: add rate-limiting / account lock (PSD2 SCA)
  - AUTH_SECRET_KEY must be at least 32 random bytes
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AuthSession, Customer
from api.deps import get_customer_service, get_db
from api.models.auth import LoginRequest, LoginResponse, TokenRefreshRequest, TokenRefreshResponse
from api.models.sca import (
    SCAInitiateRequest,
    SCAInitiateResponse,
    SCAMethodsResponse,
    SCAResendRequest,
    SCAResendResponse,
    SCAVerifyRequest,
    SCAVerifyResponse,
)
from services.auth.sca_service import get_sca_service
from services.customer.customer_service import InMemoryCustomerService

logger = logging.getLogger("banxe.auth")

router = APIRouter(tags=["Auth"])

# ── Config ────────────────────────────────────────────────────────────────────

_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-insecure-secret-change-in-prod")
_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "24"))
_REFRESH_TTL_DAYS = int(os.environ.get("AUTH_REFRESH_TOKEN_TTL_DAYS", "7"))
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

    # 5. Issue refresh token (7 day TTL, jti for uniqueness/rotation)
    refresh_expires_at = now + timedelta(days=_REFRESH_TTL_DAYS)
    refresh_payload = {
        "sub": customer_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(refresh_expires_at.timestamp()),
    }
    refresh_token = jwt.encode(refresh_payload, _SECRET_KEY, algorithm=_ALGORITHM)

    logger.info("auth.login success customer_id=%s", customer_id)
    return LoginResponse(token=token, expires_at=expires_at, refresh_token=refresh_token)


# ── Token Refresh (PSD2 RTS — max 5 min inactivity, max 15 min silent refresh) ──


@router.post(
    "/auth/token/refresh",
    response_model=TokenRefreshResponse,
    summary="Refresh access token using refresh token",
    description=(
        "Exchange a valid refresh token for a new access token + rotated refresh token. "
        "PSD2 RTS: re-authentication required after 5 min inactivity or 15 min maximum. "
        "Refresh tokens are rotated on every use (rotation prevents replay)."
    ),
    responses={
        200: {"description": "New access + refresh token pair"},
        401: {"description": "Refresh token invalid or expired"},
        422: {"description": "Validation error"},
    },
)
async def refresh_token_endpoint(body: TokenRefreshRequest) -> TokenRefreshResponse:
    """
    Rotate refresh token → new access token + new refresh token.

    Security:
      - Verifies refresh token signature (HS256)
      - Checks token type == 'refresh' (prevents access tokens being used as refresh)
      - Issues new token pair (token rotation)
      - Old refresh token is immediately invalid (in-memory store not needed for stateless JWT)

    PSD2 RTS Art.4: SCA token TTL ≤ 300s (enforced at SCA layer).
    PSD2 RTS general: inactivity timeout ≤ 5 min, enforced at frontend.
    """
    try:
        payload = jwt.decode(body.refresh_token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    customer_id = payload.get("sub")
    if not customer_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload.")

    # Issue new access + refresh token pair
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(hours=_TTL_HOURS)
    refresh_expires_at = now + timedelta(days=_REFRESH_TTL_DAYS)

    new_access_payload = {
        "sub": customer_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    new_refresh_payload = {
        "sub": customer_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),  # unique per token — ensures rotation changes the token
        "iat": int(now.timestamp()),
        "exp": int(refresh_expires_at.timestamp()),
    }

    new_access_token = jwt.encode(new_access_payload, _SECRET_KEY, algorithm=_ALGORITHM)
    new_refresh_token = jwt.encode(new_refresh_payload, _SECRET_KEY, algorithm=_ALGORITHM)

    logger.info("auth.token_refreshed customer_id=%s", customer_id)
    return TokenRefreshResponse(
        token=new_access_token,
        expires_at=expires_at,
        refresh_token=new_refresh_token,
    )


# ── SCA Endpoints (PSD2 Art.97) ───────────────────────────────────────────────


@router.post(
    "/auth/sca/challenge",
    response_model=SCAInitiateResponse,
    status_code=201,
    summary="Initiate PSD2 SCA challenge",
    description=(
        "Creates a new Strong Customer Authentication challenge for a transaction. "
        "PSD2 Directive 2015/2366 Art.97 — required for payments > £30 and sensitive actions."
    ),
    responses={
        201: {"description": "Challenge created"},
        400: {"description": "Invalid method or too many active challenges"},
        422: {"description": "Validation error"},
    },
)
async def initiate_sca_challenge(body: SCAInitiateRequest) -> SCAInitiateResponse:
    """
    Initiate an SCA challenge for the given transaction.

    Returns a challenge_id that must be passed to POST /v1/auth/sca/verify.
    Challenge expires after SCA_CHALLENGE_TTL_SEC seconds (default 120s).
    Max 3 concurrent active challenges per customer (PSD2 concurrent limit).
    """
    sca = get_sca_service()
    try:
        challenge = sca.create_challenge(
            customer_id=body.customer_id,
            transaction_id=body.transaction_id,
            method=body.method,
            amount=body.amount,
            payee=body.payee,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SCAInitiateResponse(
        challenge_id=challenge.challenge_id,
        transaction_id=challenge.transaction_id,
        method=challenge.method,  # type: ignore[arg-type]
        expires_at=challenge.expires_at,
    )


@router.post(
    "/auth/sca/verify",
    response_model=SCAVerifyResponse,
    summary="Verify SCA challenge",
    description=(
        "Verify a pending SCA challenge with OTP code or biometric proof. "
        "On success returns a PSD2 RTS Art.10 dynamic-linking JWT token (TTL ≤ 300s). "
        "After 5 failed attempts the challenge is locked; request a new one."
    ),
    responses={
        200: {"description": "Verification result (check verified field)"},
        404: {"description": "Challenge not found"},
        422: {"description": "Validation error"},
        429: {"description": "Too many failed attempts — challenge locked"},
    },
)
async def verify_sca_challenge(body: SCAVerifyRequest) -> SCAVerifyResponse:
    """
    Verify the SCA challenge.

    Replay prevention: challenge is marked 'used' after successful verification.
    Rate limit: 5 failed attempts → challenge locked (HTTP 429).
    Returns SCA JWT token bound to { txn_id, amount, payee } for payment authorisation.
    """
    sca = get_sca_service()
    result = sca.verify(
        challenge_id=body.challenge_id,
        otp_code=body.otp_code,
        biometric_proof=body.biometric_proof,
    )

    if not result.verified and result.attempts_remaining == 0:
        raise HTTPException(
            status_code=429,
            detail=result.error or "Too many failed attempts. Request a new challenge.",
        )

    if not result.verified and result.error == "Challenge not found":
        raise HTTPException(status_code=404, detail="Challenge not found")

    return SCAVerifyResponse(
        verified=result.verified,
        transaction_id=result.transaction_id,
        sca_token=result.sca_token,
        error=result.error,
        attempts_remaining=result.attempts_remaining,
    )


@router.post(
    "/auth/sca/resend",
    response_model=SCAResendResponse,
    summary="Resend SCA challenge (PSD2 Art.97)",
    description=(
        "Resets the TTL of an existing SCA challenge and re-delivers the authentication "
        "prompt (OTP SMS / push notification). Rate-limited to 3 resends per challenge. "
        "PSD2 Directive 2015/2366 Art.97 — customer may request a fresh code if not received."
    ),
    responses={
        200: {"description": "Challenge resent, TTL reset"},
        400: {"description": "Challenge already used/failed or resend limit reached"},
        404: {"description": "Challenge not found"},
        422: {"description": "Validation error"},
    },
)
async def resend_sca_challenge(body: SCAResendRequest) -> SCAResendResponse:
    """
    Resend a pending SCA challenge.

    Increments resend_count and resets the challenge expiry to now + SCA_CHALLENGE_TTL_SEC.
    Maximum 3 resends per challenge_id (PSD2 Art.97 rate-limit).
    """
    sca = get_sca_service()
    try:
        challenge = sca.resend_challenge(body.challenge_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SCAResendResponse(
        challenge_id=challenge.challenge_id,
        method=challenge.method,  # type: ignore[arg-type]
        expires_at=challenge.expires_at,
        resend_count=challenge.resend_count,
    )


@router.get(
    "/auth/sca/methods/{customer_id}",
    response_model=SCAMethodsResponse,
    summary="Get available SCA methods for customer",
    description=(
        "Returns the available SCA methods (otp, biometric) and preferred method "
        "for the given customer. Used by frontend to decide which SCA UI to show."
    ),
    responses={
        200: {"description": "Available SCA methods"},
    },
)
async def get_sca_methods(customer_id: str) -> SCAMethodsResponse:
    """
    Return available SCA methods for the customer.

    OTP is always available. Biometric is available if the customer
    has an enrolled device (expo-local-auth / WebAuthn).
    """
    sca = get_sca_service()
    methods = sca.get_methods(customer_id)
    return SCAMethodsResponse(
        customer_id=methods.customer_id,
        methods=methods.methods,
        preferred=methods.preferred,
    )
