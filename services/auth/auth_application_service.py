from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import os
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AuthSession, Customer
from api.models.auth import LoginResponse, TokenRefreshResponse
from services.auth.token_manager import TokenManager, TokenValidationError
from services.auth.token_manager_port import TokenManagerPort

logger = logging.getLogger("banxe.auth.app")

DEV_PIN = os.environ.get("AUTH_DEV_PIN", os.environ.get("AUTHDEVPIN", "123456"))


class AuthApplicationError(Exception):
    def __init__(self, message: str, code: str = "auth_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(slots=True)
class CustomerIdentity:
    customer_id: str
    email: str


class AuthApplicationService:
    """Application boundary for auth login/refresh orchestration."""

    def __init__(
        self,
        token_manager: TokenManagerPort | None = None,
        iam_port: Any = None,
        sca_service: Any = None,
    ) -> None:
        self.token_manager = token_manager or TokenManager()
        self.iam_port = iam_port
        self.sca_service = sca_service

    async def _get_customer_by_email_db(
        self,
        db: AsyncSession,
        email: str,
    ) -> Customer | None:
        result = await db.execute(select(Customer).where(Customer.email == email))
        return result.scalar_one_or_none()

    def _get_customer_by_email_memory(
        self,
        svc: Any,
        email: str,
    ) -> tuple[str, str] | None:
        if svc is None:
            return None
        for c in svc.list_customers():
            if c.metadata.get("email") == email:
                return c.customer_id, email
        return None

    async def _resolve_customer_identity(
        self,
        db: AsyncSession,
        svc: Any,
        email: str,
    ) -> CustomerIdentity:
        customer_id: str | None = None
        customer_email = email

        try:
            db_customer = await self._get_customer_by_email_db(db, email)
            if db_customer is not None:
                customer_id = db_customer.customer_id
                customer_email = db_customer.email
        except Exception:
            logger.warning("auth.login db_lookup_failed falling_back_to_memory")

        if customer_id is None:
            memory_result = self._get_customer_by_email_memory(svc, email)
            if memory_result is not None:
                customer_id, customer_email = memory_result

        if customer_id is None:
            raise AuthApplicationError("Invalid email or PIN", code="invalid_credentials")

        return CustomerIdentity(customer_id=customer_id, email=customer_email)

    def _validate_pin(self, pin: str) -> None:
        if pin != DEV_PIN:
            raise AuthApplicationError("Invalid email or PIN", code="invalid_credentials")

    async def _persist_session_best_effort(
        self,
        db: AsyncSession,
        customer_id: str,
        access_token: str,
        expires_at: datetime,
        user_agent: str | None,
    ) -> None:
        try:
            session = AuthSession(
                session_id=str(uuid.uuid4()),
                customer_id=customer_id,
                token_prefix=access_token[:16],
                expires_at=expires_at,
                user_agent=user_agent,
            )
            db.add(session)
            await db.flush()
        except Exception:
            logger.warning("auth.login session_persist_failed customer_id=%s", customer_id)

    async def login(
        self,
        *,
        db: AsyncSession,
        svc: Any,
        email: str,
        pin: str,
        user_agent: str | None = None,
    ) -> LoginResponse:
        identity = await self._resolve_customer_identity(db=db, svc=svc, email=email)
        self._validate_pin(pin)

        access_token, expires_at = self.token_manager.issue_access_token(identity.customer_id)
        refresh_token, _refresh_expires_at = self.token_manager.issue_refresh_token(
            identity.customer_id
        )

        await self._persist_session_best_effort(
            db=db,
            customer_id=identity.customer_id,
            access_token=access_token,
            expires_at=expires_at,
            user_agent=user_agent,
        )

        logger.info("auth.login success customer_id=%s", identity.customer_id)
        return LoginResponse(
            token=access_token,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> TokenRefreshResponse:
        try:
            access_token, new_refresh_token, access_expires_at, _refresh_expires_at = (
                self.token_manager.rotate(refresh_token)
            )
        except TokenValidationError as exc:
            raise AuthApplicationError(exc.message, code=exc.code) from exc

        return TokenRefreshResponse(
            token=access_token,
            expires_at=access_expires_at,
            refresh_token=new_refresh_token,
        )


def get_auth_application_service() -> AuthApplicationService:
    """Dependency provider for FastAPI auth application service."""
    return AuthApplicationService()
