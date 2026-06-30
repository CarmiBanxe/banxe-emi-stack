"""
sandbox_api.py — FastAPI router for sandbox service
GAP-042 M-sandbox: Sandbox Mock Rails Service
banxe-emi-stack

Endpoints for seeding test accounts and advancing payment states.
All amounts are DecimalString (never float). Development-only service.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.sandbox.sandbox_service import InMemorySandboxService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

_service = InMemorySandboxService()


class SeedAccountRequest(BaseModel):
    """Request to seed a test account."""

    account_id: str = Field(..., description="Unique account ID")
    holder_name: str = Field(..., description="Account holder name")
    currency: str = Field(..., description="ISO-4217 currency code (e.g. GBP, EUR)")
    balance: str = Field(..., description="Starting balance as decimal string (e.g. '1000.50')")


class SandboxAccountResponse(BaseModel):
    """Response containing a seeded account."""

    account_id: str
    holder_name: str
    currency: str
    balance: str  # DecimalString: never float


class AdvancePaymentRequest(BaseModel):
    """Request to advance a payment's status."""

    target_status: str = Field(..., description="Target status (PROCESSING, COMPLETED, FAILED)")


class PaymentTransitionResponse(BaseModel):
    """Response containing a payment state transition."""

    payment_id: str
    from_status: str
    to_status: str


class ResetResponse(BaseModel):
    """Response to reset endpoint."""

    reset: bool
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


@router.post("/accounts")
async def seed_account(req: SeedAccountRequest) -> SandboxAccountResponse:
    """
    Seed a test account.

    Args:
        account_id: Unique account ID
        holder_name: Account holder name
        currency: ISO-4217 currency code
        balance: Starting balance as decimal string

    Returns:
        Created/updated SandboxAccountResponse

    Raises:
        HTTPException 400: if balance is negative or invalid
    """
    try:
        balance = Decimal(req.balance)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Invalid balance: {exc}") from exc

    try:
        account = _service.seed_account(
            account_id=req.account_id,
            holder_name=req.holder_name,
            currency=req.currency,
            balance=balance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SandboxAccountResponse(
        account_id=account.account_id,
        holder_name=account.holder_name,
        currency=account.currency,
        balance=str(account.balance),
    )


@router.get("/accounts")
async def list_accounts() -> list[SandboxAccountResponse]:
    """
    List all seeded accounts.

    Returns:
        List of SandboxAccountResponse objects
    """
    accounts = _service.list_accounts()
    return [
        SandboxAccountResponse(
            account_id=acc.account_id,
            holder_name=acc.holder_name,
            currency=acc.currency,
            balance=str(acc.balance),
        )
        for acc in accounts
    ]


@router.get("/accounts/{account_id}")
async def get_account(account_id: str) -> SandboxAccountResponse:
    """
    Get a seeded account by ID.

    Args:
        account_id: Account ID to retrieve

    Returns:
        SandboxAccountResponse

    Raises:
        HTTPException 404: if account not found
    """
    account = _service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    return SandboxAccountResponse(
        account_id=account.account_id,
        holder_name=account.holder_name,
        currency=account.currency,
        balance=str(account.balance),
    )


@router.post("/payments/{payment_id}/advance")
async def advance_payment(
    payment_id: str,
    req: AdvancePaymentRequest,
) -> PaymentTransitionResponse:
    """
    Advance a payment's status.

    Valid transitions:
      - PENDING → PROCESSING
      - PROCESSING → COMPLETED
      - PROCESSING → FAILED

    Args:
        payment_id: Payment ID to advance
        target_status: Target status

    Returns:
        PaymentTransitionResponse

    Raises:
        HTTPException 400: if transition is invalid
        HTTPException 404: if payment not registered
    """
    _service.register_payment(payment_id)
    try:
        transition = _service.advance_payment(payment_id, req.target_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PaymentTransitionResponse(
        payment_id=transition.payment_id,
        from_status=transition.from_status,
        to_status=transition.to_status,
    )


@router.delete("/reset")
async def reset() -> ResetResponse:
    """
    Reset all sandbox state (accounts + payments).

    Returns:
        ResetResponse confirming reset
    """
    _service.reset()
    return ResetResponse(reset=True, message="Sandbox state cleared")


@router.get("/health")
async def health() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        HealthResponse with status
    """
    return HealthResponse(status="ok", service="sandbox")
