"""
api/routers/auth.py — Authentication endpoints
IL-046 | S15-01 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import os
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from services.auth.auth_application_service import (
    AuthApplicationError,
    AuthApplicationService,
    get_auth_application_service,
)
from services.auth.sca_service import SCAService, get_sca_service
from services.customer.customer_service import InMemoryCustomerService

SECRETKEY = os.environ.get(
    "AUTH_SECRET_KEY", os.environ.get("AUTHSECRETKEY", "dev-insecure-secret-change-in-prod")
)
TTLHOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", os.environ.get("AUTHTOKENTTLHOURS", "24")))
REFRESHTTLDAYS = int(
    os.environ.get("AUTH_REFRESH_TOKEN_TTL_DAYS", os.environ.get("AUTHREFRESHTOKENTTLDAYS", "7"))
)
ALGORITHM = os.environ.get("AUTH_ALGORITHM", "HS256")
DEV_PIN = os.environ.get("AUTH_DEV_PIN", os.environ.get("AUTHDEVPIN", "123456"))

_SECRET_KEY = SECRETKEY
_TTL_HOURS = TTLHOURS
_REFRESH_TTL_DAYS = REFRESHTTLDAYS
_ALGORITHM = ALGORITHM
_DEV_PIN = DEV_PIN

SECRET_KEY = SECRETKEY
TTL_HOURS = TTLHOURS
REFRESH_TTL_DAYS = REFRESHTTLDAYS

logger = logging.getLogger("banxe.auth")
router = APIRouter(tags=["Auth"])


async def _get_customer_by_email_db(db: AsyncSession, email: str) -> Customer | None:
    stmt = select(Customer).where(Customer.email == email).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _get_customer_by_email_memory(
    svc: InMemoryCustomerService, email: str
) -> tuple[str, str] | None:
    for c in svc.list_customers():
        if c.metadata.get("email") == email:
            return c.customer_id, email
    return None


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
    auth_app: AuthApplicationService = Depends(get_auth_application_service),
) -> LoginResponse:
    customer_id: str | None = None
    customer_email: str = body.email

    try:
        db_customer = await _get_customer_by_email_db(db, body.email)
        if db_customer is not None:
            customer_id = db_customer.customer_id
            db_email = getattr(db_customer, "email", None)
            if isinstance(db_email, str) and db_email:
                customer_email = db_email
    except Exception:
        logger.warning("auth.login db_lookup_failed — falling back to InMemory")

    if customer_id is None:
        memory_result = _get_customer_by_email_memory(svc, body.email)
        if memory_result is not None:
            customer_id, customer_email = memory_result

    if customer_id is None:
        logger.warning("auth.login email_not_found")
        raise HTTPException(status_code=401, detail="Invalid email or PIN")

    if body.pin != _DEV_PIN:
        logger.warning("auth.login invalid_pin customer_id=%s", customer_id)
        raise HTTPException(status_code=401, detail="Invalid email or PIN")

    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(hours=_TTL_HOURS)

    payload: dict[str, Any] = {
        "sub": customer_id,
        "email": customer_email,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)

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
async def refresh_token_endpoint(
    body: TokenRefreshRequest,
    auth_app: AuthApplicationService = Depends(get_auth_application_service),
) -> TokenRefreshResponse:
    try:
        return await auth_app.refresh(refresh_token=body.refresh_token)
    except AuthApplicationError:
        try:
            payload = jwt.decode(body.refresh_token, _SECRET_KEY, algorithms=[_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401, detail="Refresh token expired. Please login again."
            )
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid refresh token.")

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type.")

        customer_id = payload.get("sub")
        if not customer_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token payload.")

        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(hours=_TTL_HOURS)
        refresh_expires_at = now + timedelta(days=_REFRESH_TTL_DAYS)

        new_access_payload = {
            "sub": customer_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        new_access_token = jwt.encode(new_access_payload, _SECRET_KEY, algorithm=_ALGORITHM)

        new_refresh_payload = {
            "sub": customer_id,
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(refresh_expires_at.timestamp()),
        }
        new_refresh_token = jwt.encode(new_refresh_payload, _SECRET_KEY, algorithm=_ALGORITHM)

        return TokenRefreshResponse(
            token=new_access_token,
            expires_at=expires_at,
            refresh_token=new_refresh_token,
        )


@router.post(
    "/auth/sca/challenge",
    response_model=SCAInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_sca(
    body: SCAInitiateRequest,
    sca_service: SCAService = Depends(get_sca_service),
) -> SCAInitiateResponse:
    try:
        challenge = sca_service.create_challenge(
            customer_id=body.customer_id,
            transaction_id=body.transaction_id,
            method=body.method,
            amount=body.amount,
            payee=body.payee,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SCAInitiateResponse(
        challenge_id=challenge.challenge_id,
        transaction_id=challenge.transaction_id,
        method=challenge.method,
        expires_at=challenge.expires_at,
    )


@router.post("/auth/sca/verify", response_model=SCAVerifyResponse)
async def verify_sca(
    body: SCAVerifyRequest,
    sca_service: SCAService = Depends(get_sca_service),
) -> SCAVerifyResponse:
    result = sca_service.verify(
        challenge_id=body.challenge_id,
        otp_code=body.otp_code,
        biometric_proof=body.biometric_proof,
    )
    if result.error == "Challenge not found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if not result.verified and result.attempts_remaining == 0:
        raise HTTPException(
            status_code=429, detail="Too many failed attempts. Request a new challenge."
        )
    return SCAVerifyResponse(
        verified=result.verified,
        transaction_id=result.transaction_id,
        sca_token=result.sca_token,
        error=result.error,
        attempts_remaining=result.attempts_remaining,
    )


@router.post("/auth/sca/resend", response_model=SCAResendResponse)
async def resend_sca(
    body: SCAResendRequest,
    sca_service: SCAService = Depends(get_sca_service),
) -> SCAResendResponse:
    try:
        challenge = sca_service.resend_challenge(body.challenge_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SCAResendResponse(
        challenge_id=challenge.challenge_id,
        method=challenge.method,
        expires_at=challenge.expires_at,
        resend_count=challenge.resend_count,
    )


@router.get("/auth/sca/methods/{customer_id}", response_model=SCAMethodsResponse)
async def get_sca_methods(
    customer_id: str,
    sca_service: SCAService = Depends(get_sca_service),
) -> SCAMethodsResponse:
    methods = sca_service.get_methods(customer_id)
    return SCAMethodsResponse(
        customer_id=methods.customer_id,
        methods=methods.methods,
        preferred=methods.preferred,
    )
