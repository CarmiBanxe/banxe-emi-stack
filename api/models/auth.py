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
    token: str = Field(..., description="JWT Bearer token")
    expires_at: datetime = Field(..., description="Token expiry (UTC)")
