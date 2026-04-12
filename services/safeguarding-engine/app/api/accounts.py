"""Safeguarding accounts CRUD API endpoints."""

import uuid
from fastapi import APIRouter, Depends

from app.schemas.safeguarding import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    BalanceSnapshotCreate,
)
from app.dependencies import get_safeguarding_service

router = APIRouter(prefix="/accounts")


@router.post("", response_model=AccountResponse)
async def create_account(data: AccountCreate, service=Depends(get_safeguarding_service)):
    """Register a safeguarding bank account."""
    return await service.create_account(data)


@router.get("")
async def list_accounts(service=Depends(get_safeguarding_service)):
    """List all safeguarding accounts."""
    raise NotImplementedError("Implement in Phase 3.6")


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(account_id: uuid.UUID, service=Depends(get_safeguarding_service)):
    """Account details + balance history."""
    raise NotImplementedError("Implement in Phase 3.6")


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(account_id: uuid.UUID, data: AccountUpdate, service=Depends(get_safeguarding_service)):
    """Update account metadata."""
    return await service.update_account(account_id, data)


@router.post("/{account_id}/balance")
async def record_balance(account_id: uuid.UUID, data: BalanceSnapshotCreate, service=Depends(get_safeguarding_service)):
    """Record balance snapshot from bank."""
    return await service.record_balance_snapshot(account_id, data)
