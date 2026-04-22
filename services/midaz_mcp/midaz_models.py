"""
services/midaz_mcp/midaz_models.py
Pydantic models for Midaz CBS integration (IL-MCP-01).
I-01: all amounts are Decimal strings.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_validator


class Organization(BaseModel):
    org_id: str
    name: str
    legal_name: str
    country: str = "GB"
    model_config = {"frozen": True}


class Ledger(BaseModel):
    ledger_id: str
    org_id: str
    name: str
    model_config = {"frozen": True}


class Asset(BaseModel):
    asset_id: str
    ledger_id: str
    code: str
    scale: int = 2
    model_config = {"frozen": True}


class Account(BaseModel):
    account_id: str
    ledger_id: str
    asset_id: str
    name: str
    account_type: str = "deposit"
    model_config = {"frozen": True}


class TransactionEntry(BaseModel):
    account_id: str
    amount: str  # Decimal as string (I-01)
    direction: str  # "DEBIT" or "CREDIT"

    @field_validator("amount")
    @classmethod
    def validate_amount_decimal(cls, v: str) -> str:
        d = Decimal(v)
        if d < Decimal("0"):
            raise ValueError("Amount must be non-negative (I-01)")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("DEBIT", "CREDIT"):
            raise ValueError("direction must be DEBIT or CREDIT")
        return v

    model_config = {"frozen": True}


class Transaction(BaseModel):
    transaction_id: str
    ledger_id: str
    entries: list[TransactionEntry]
    status: str = "PENDING"
    model_config = {"frozen": True}


class Balance(BaseModel):
    account_id: str
    asset_code: str
    amount: str  # Decimal as string (I-01)
    model_config = {"frozen": True}
