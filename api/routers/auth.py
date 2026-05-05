"""
api/routers/auth.py — Authentication endpoints (thin router)
IL-046 | S15-01 | banxe-emi-stack

Sprint 3 refactor: login/refresh orchestration extracted to AuthApplicationService.
Sprint 4 refactor: SCA orchestration extracted to ScaApplicationService.

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
from services.auth.auth_application_service import (
    AuthApplicationError,
    AuthApplicationService,
    get_auth_application_service,
)
from services.auth.sca_application_service import (
    ScaApplicationError,
    ScaApplicationService,
)
from services.customer.customer_service import InMemoryCustomerService

logger = logging.getLogger("banxe.auth")
router = APIRouter(tags=["Auth"])

# Re-export get_sca_service so tests can monkeypatch
# api.routers.auth.get_sca_service. The router-local factory below builds a
# fresh ScaApplicationService bound to the (possibly patched) sca_service
# instance so monkeypatch works end-to-end.
from api.deps import get_two_factor_port  # noqa: E402
from services.auth.sca_service import get_sca_service  # noqa: E402
from services.auth.two_factor import TOTPService  # noqa: E402


def get_sca_application_service(
    two_factor: TOTPService = Depends(get_two_factor_port),
) -> ScaApplicationService:
    """Router-local DI provider: builds ScaApplicationService bound to the
    current get_sca_service() result with TOTPService injected as
    TwoFactorPort for production OTP verification (Sprint 4 Track A Block 7).

    Tests can monkey-patch get_sca_service to return a port-less SCAService
    instance, in which case the legacy pyotp/deterministic fallback is used
    (see tests/test_api_sca.py::fresh_sca_service).
    """
    try:
        sca_service = get_sca_service(two_factor=two_factor)
    except TypeError:
        sca_service = get_sca_service()
    return ScaApplicationService(sca_service=sca_service)


_ERROR_CODE_TO_HTTP: dict[str, int] = {
    "invalid_credentials": 401,
    "invalid_token": 401,
    "token_expired": 401,
    "invalid_token_type": 401,
}


_SCA_ERROR_CODE_TO_HTTP: dict[str, int] = {
    "invalid_method": 400,
    "too_many_active": 400,
    "challenge_not_found": 404,
    "too_many_attempts": 429,
    "resend_rejected": 400,
}


def _map_auth_error(exc: AuthApplicationError) -> HTTPException:
    """Translate AuthApplicationError -> HTTPException with stable status mapping."""
    status_code = _ERROR_CODE_TO_HTTP.get(exc.code, 401)
    return HTTPException(status_code=status_code, detail=exc.message)


def _map_sca_error(exc: ScaApplicationError) -> HTTPException:
    """Translate ScaApplicationError -> HTTPException with stable status mapping."""
    status_code = _SCA_ERROR_CODE_TO_HTTP.get(exc.code, 400)
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
# SCA endpoints — Sprint 4 Track A: delegated to ScaApplicationService.
# Router is now a thin transport mapping; no SCA business branching.
# ---------------------------------------------------------------------------


@router.post(
    "/auth/sca/challenge",
    response_model=SCAInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_sca(
    body: SCAInitiateRequest,
    sca_app: ScaApplicationService = Depends(get_sca_application_service),
) -> SCAInitiateResponse:
    try:
        return sca_app.initiate_challenge(
            customer_id=body.customer_id,
            transaction_id=body.transaction_id,
            method=body.method,
            amount=body.amount,
            payee=body.payee,
        )
    except ScaApplicationError as exc:
        raise _map_sca_error(exc) from exc


@router.post("/auth/sca/verify", response_model=SCAVerifyResponse)
async def verify_sca(
    body: SCAVerifyRequest,
    sca_app: ScaApplicationService = Depends(get_sca_application_service),
) -> SCAVerifyResponse:
    try:
        return sca_app.verify_challenge(
            challenge_id=body.challenge_id,
            otp_code=body.otp_code,
            biometric_proof=body.biometric_proof,
        )
    except ScaApplicationError as exc:
        raise _map_sca_error(exc) from exc


@router.post("/auth/sca/resend", response_model=SCAResendResponse)
async def resend_sca(
    body: SCAResendRequest,
    sca_app: ScaApplicationService = Depends(get_sca_application_service),
) -> SCAResendResponse:
    try:
        return sca_app.resend_challenge(challenge_id=body.challenge_id)
    except ScaApplicationError as exc:
        raise _map_sca_error(exc) from exc


@router.get("/auth/sca/methods/{customer_id}", response_model=SCAMethodsResponse)
async def get_sca_methods(
    customer_id: str,
    sca_app: ScaApplicationService = Depends(get_sca_application_service),
) -> SCAMethodsResponse:
    return sca_app.list_methods(customer_id=customer_id)
