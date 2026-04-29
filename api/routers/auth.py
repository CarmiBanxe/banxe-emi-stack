"""
api/routers/auth.py — Authentication endpoints (thin router)
IL-046 | S15-01 | banxe-emi-stack

Sprint 3 refactor: orchestration extracted to AuthApplicationService.
Router only handles HTTP concerns: request parsing, exception mapping, response shaping.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_customer_service, get_db
from api.models.auth import (
    LoginRequest,
    LoginResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from api.models.sca import (
    SCAInitiateRequest,
    SCAInitiateResponse,
    SCAMethodsResponse,
    SCAResendRequest,
    SCAResendResponse,
    SCAVerifyRequest,
    SCAVerifyResponse,
)
from api.models.sca_adapters import (
    to_sca_initiate_response,
    to_sca_methods_response,
    to_sca_resend_response,
    to_sca_verify_response,
)
from services.auth.auth_application_service import (
    AuthApplicationError,
    AuthApplicationService,
    get_auth_application_service,
)
from services.auth.sca_service import get_sca_service
from services.auth.sca_service_port import ScaServicePort
from services.customer.customer_service import InMemoryCustomerService

logger = logging.getLogger("banxe.auth")
router = APIRouter(tags=["Auth"])


_ERROR_CODE_TO_HTTP: dict[str, int] = {
    "invalid_credentials": 401,
    "invalid_token": 401,
    "token_expired": 401,
    "invalid_token_type": 401,
}


def _map_auth_error(exc: AuthApplicationError) -> HTTPException:
    """Translate AuthApplicationError -> HTTPException with stable status mapping."""
    status_code = _ERROR_CODE_TO_HTTP.get(exc.code, 401)
    return HTTPException(status_code=status_code, detail=exc.message)


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
    """Thin delegation: identity resolution, PIN validation, token issuance, session
    persistence are all handled by AuthApplicationService.login()."""
    try:
        return await auth_app.login(
            db=db,
            svc=svc,
            email=body.email,
            pin=body.pin,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthApplicationError as exc:
        raise _map_auth_error(exc) from exc


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
    """Thin delegation: token rotation handled by AuthApplicationService.refresh()."""
    try:
        return await auth_app.refresh(refresh_token=body.refresh_token)
    except AuthApplicationError as exc:
        raise _map_auth_error(exc) from exc


# ---------------------------------------------------------------------------
# SCA endpoints — unchanged (out of Sprint 3 scope, will be extracted in Sprint 4-5)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/sca/challenge",
    response_model=SCAInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_sca(
    body: SCAInitiateRequest,
    sca_service: ScaServicePort = Depends(get_sca_service),
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
    return to_sca_initiate_response(challenge)


@router.post("/auth/sca/verify", response_model=SCAVerifyResponse)
async def verify_sca(
    body: SCAVerifyRequest,
    sca_service: ScaServicePort = Depends(get_sca_service),
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
    return to_sca_verify_response(result)


@router.post("/auth/sca/resend", response_model=SCAResendResponse)
async def resend_sca(
    body: SCAResendRequest,
    sca_service: ScaServicePort = Depends(get_sca_service),
) -> SCAResendResponse:
    try:
        challenge = sca_service.resend_challenge(body.challenge_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_sca_resend_response(challenge)


@router.get("/auth/sca/methods/{customer_id}", response_model=SCAMethodsResponse)
async def get_sca_methods(
    customer_id: str,
    sca_service: ScaServicePort = Depends(get_sca_service),
) -> SCAMethodsResponse:
    methods = sca_service.get_methods(customer_id)
    return to_sca_methods_response(methods)
