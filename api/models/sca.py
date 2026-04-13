"""
api/models/sca.py — Pydantic v2 schemas for PSD2 SCA API
S15-01 | PSD2 Directive 2015/2366 Art.97 | banxe-emi-stack

Endpoints:
  POST /v1/auth/sca/challenge — initiate SCA challenge
  POST /v1/auth/sca/verify   — verify SCA response
  GET  /v1/auth/sca/methods/{customer_id} — available methods
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SCAInitiateRequest(BaseModel):
    customer_id: str = Field(..., description="Customer identifier")
    transaction_id: str = Field(..., description="Transaction to authenticate")
    method: Literal["otp", "biometric"] = Field(..., description="SCA method")
    amount: str | None = Field(
        None,
        description="Transaction amount as decimal string (PSD2 RTS Art.10 dynamic linking)",
        examples=["150.00"],
    )
    payee: str | None = Field(
        None,
        description="Payee name (PSD2 RTS Art.10 dynamic linking)",
    )

    @field_validator("amount")
    @classmethod
    def amount_must_be_decimal_string(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            from decimal import Decimal

            Decimal(v)
        except (ValueError, Exception):
            raise ValueError("amount must be a valid decimal string (e.g. '150.00')")
        return v


class SCAInitiateResponse(BaseModel):
    challenge_id: str = Field(..., description="Unique SCA challenge identifier")
    transaction_id: str = Field(..., description="Bound transaction identifier")
    method: Literal["otp", "biometric"] = Field(..., description="SCA method to use")
    expires_at: datetime = Field(..., description="Challenge expiry (UTC)")
    message: str = Field(
        default="SCA challenge created. Complete authentication within the time limit.",
        description="User-facing instruction",
    )


class SCAVerifyRequest(BaseModel):
    challenge_id: str = Field(..., description="Challenge ID from initiate response")
    otp_code: str | None = Field(
        None,
        min_length=6,
        max_length=6,
        description="6-digit TOTP code (required for method=otp)",
    )
    biometric_proof: str | None = Field(
        None,
        description="Biometric assertion proof (required for method=biometric)",
    )

    @field_validator("otp_code")
    @classmethod
    def otp_must_be_digits(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.isdigit():
            raise ValueError("OTP code must contain only digits")
        return v


class SCAVerifyResponse(BaseModel):
    verified: bool = Field(..., description="Whether SCA was successful")
    transaction_id: str = Field(..., description="Bound transaction identifier")
    sca_token: str | None = Field(
        None,
        description="PSD2 RTS Art.10 JWT token (only if verified=True). Include in payment Authorization header.",
    )
    error: str | None = Field(None, description="Error message (only if verified=False)")
    attempts_remaining: int | None = Field(
        None,
        description="Remaining verification attempts before challenge locks",
    )


class SCAMethodsResponse(BaseModel):
    customer_id: str = Field(..., description="Customer identifier")
    methods: list[str] = Field(..., description="Available SCA methods")
    preferred: str = Field(..., description="Recommended SCA method for this customer")
