"""
api/models/auth.py — Pydantic v2 schemas for Auth API
IL-046 | banxe-emi-stack

POST /v1/auth/login request + response models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(..., description="Customer email address")
    pin: str = Field(..., min_length=6, max_length=6, description="6-digit numeric PIN")

    @field_validator("pin")
    @classmethod
    def pin_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("PIN must contain only digits")
        return v


class LoginResponse(BaseModel):
    token: str = Field(..., description="JWT Bearer token (access token)")
    expires_at: datetime = Field(..., description="Access token expiry (UTC)")
    refresh_token: str | None = Field(
        None,
        description="JWT refresh token — valid for 7 days. Pass to POST /v1/auth/token/refresh.",
    )
    token_type: str = Field(default="bearer", description="Token type")


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token from login response")


class TokenRefreshResponse(BaseModel):
    token: str = Field(..., description="New JWT Bearer token (access token)")
    expires_at: datetime = Field(..., description="New access token expiry (UTC)")
    refresh_token: str = Field(..., description="New refresh token (rotated)")
    token_type: str = Field(default="bearer", description="Token type")
