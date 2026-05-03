"""
services/auth/sca_models.py — SCA domain types
S15-01 | PSD2 Directive 2015/2366 Art.97 | banxe-emi-stack

Sprint 4 refactor: domain types extracted from sca_service.py to break
circular import between sca_service_port and sca_service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SCAChallenge:
    """A pending SCA challenge for a payment or sensitive action."""

    challenge_id: str
    customer_id: str
    transaction_id: str
    method: str
    status: str
    created_at: datetime
    expires_at: datetime
    amount: str | None = None
    payee: str | None = None
    attempt_count: int = 0
    resend_count: int = 0


@dataclass
class SCAVerifyResult:
    """Result of an SCA challenge verification attempt."""

    verified: bool
    transaction_id: str
    sca_token: str | None = None
    error: str | None = None
    attempts_remaining: int | None = None


@dataclass
class SCAMethods:
    """Available SCA methods for a customer."""

    customer_id: str
    methods: list[str]
    preferred: str
