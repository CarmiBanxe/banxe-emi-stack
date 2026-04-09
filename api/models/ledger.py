"""
api/models/ledger.py — Pydantic v2 schemas for Ledger API
IL-046 | banxe-emi-stack

Wraps Midaz CBS responses. Amounts as strings (I-05).
"""

from __future__ import annotations

from pydantic import BaseModel


class AccountBalanceResponse(BaseModel):
    account_id: str
    available: str
    total: str
    currency: str
    on_hold: str | None = None


class AccountResponse(BaseModel):
    account_id: str
    name: str
    type: str
    currency: str
    status: str


class AccountListResponse(BaseModel):
    accounts: list[AccountResponse]
    total: int
