"""
api/deps.py — FastAPI dependency injection
IL-046 | banxe-emi-stack

Provides service instances via FastAPI Depends().
In sandbox/test mode: InMemory/Stub adapters.
In production: real adapters selected via env vars.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
import os
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.safeguarding.buffered_audit_port import BufferedAuditPort

    from services.recon.recon_engine import ReconciliationEngine

from services.customer.customer_service import InMemoryCustomerService
from services.database import AsyncSessionLocal
from services.kyc.mock_kyc_workflow import MockKYCWorkflow
from services.ledger.midaz_adapter import MidazLedgerAdapter, StubLedgerAdapter
from services.payment.mock_payment_adapter import MockPaymentAdapter
from services.payment.payment_service import PaymentService
from services.statements.statement_service import (
    AccountStatementService,
    InMemoryTransactionRepository,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session per request — commit on success, rollback on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache(maxsize=1)
def get_customer_service() -> InMemoryCustomerService:
    return InMemoryCustomerService()


@lru_cache(maxsize=1)
def get_kyc_service() -> MockKYCWorkflow:
    return MockKYCWorkflow()


@lru_cache(maxsize=1)
def get_payment_service() -> PaymentService:
    """Payment service with ledger integration.

    PAYMENT_ADAPTER env var controls rail adapter:
      "mock"   -> MockPaymentAdapter (default, no API key needed)
      "modulr" -> ModulrPaymentAdapter (requires MODULR_API_KEY)

    LEDGER_ADAPTER env var controls ledger:
      "stub"  -> StubLedgerAdapter (default, in-memory)
      "midaz" -> MidazLedgerAdapter (requires MIDAZ_BASE_URL)
    """
    adapter_name = os.environ.get("PAYMENT_ADAPTER", "mock")
    if adapter_name == "mock":
        rail = MockPaymentAdapter()
    else:
        from services.payment.modulr_client import ModulrPaymentAdapter

        rail = ModulrPaymentAdapter()

    ledger_name = os.environ.get("LEDGER_ADAPTER", "stub")
    if ledger_name == "midaz":
        ledger = MidazLedgerAdapter()
    else:
        ledger = StubLedgerAdapter()

    return PaymentService(rail=rail, ch_client=None, ledger_port=ledger)


def get_ledger_base_url() -> str:
    """Midaz ledger base URL from env (falls back to sandbox)."""
    return os.environ.get("MIDAZ_BASE_URL", "http://localhost:8095")


@lru_cache(maxsize=1)
def get_statement_service() -> AccountStatementService:
    """Account statement service — InMemory repo (sandbox/test).
    In production: swap InMemoryTransactionRepository for ClickHouseTransactionRepository.
    """
    return AccountStatementService(repo=InMemoryTransactionRepository())


# --- Append to api/deps.py ---
# ── IAM / Auth / 2FA DI (P0 closure — auth/IAM/2FA wiring) ──────────────────

from fastapi import Header, HTTPException
from fastapi import Security as FastAPISecurity

from services.auth.sca_service import InMemorySCAStore, SCAService
from services.auth.two_factor import TOTPService
from services.iam.iam_port import IAMPort, Permission, UserIdentity
from services.iam.mock_iam_adapter import get_iam_adapter


@lru_cache(maxsize=1)
def get_iam() -> IAMPort:
    """IAM adapter — MockIAMAdapter (default) or KeycloakAdapter (IAM_ADAPTER=keycloak)."""
    return get_iam_adapter()


@lru_cache(maxsize=1)
def get_totp_service() -> TOTPService:
    """TOTP 2FA service (RFC 6238)."""
    return TOTPService()


# TwoFactorPort alias: TOTPService implements the TwoFactorPort Protocol
# structurally. Use get_two_factor_port at injection sites where the
# semantic dependency is the 2FA verification port (Sprint 4 Track A Block 7).
get_two_factor_port = get_totp_service


@lru_cache(maxsize=1)
def get_sca_service_di() -> SCAService:
    """PSD2 SCA challenge service — DI-managed singleton."""
    return SCAService(store=InMemorySCAStore())


async def require_auth(
    authorization: str = Header(..., description="Bearer <token>"),
) -> UserIdentity:
    """
    FastAPI dependency: extract Bearer token, validate via IAMPort.
    Returns UserIdentity or raises 401.
    Usage: user: UserIdentity = Depends(require_auth)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization[7:]
    iam = get_iam()
    identity = iam.validate_token(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return identity


def require_permission(perm: Permission):
    """
    Factory: returns a FastAPI dependency that checks a specific permission.
    Usage: Depends(require_permission(Permission.FILE_SAR))
    """

    async def _check(
        identity: UserIdentity = FastAPISecurity(require_auth),
    ) -> UserIdentity:
        iam = get_iam()
        if not iam.authorize(identity, perm):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {perm.value} required",
            )
        return identity

    return _check


def require_role(*roles):
    """
    Factory: returns a FastAPI dependency that checks role membership.
    Usage: Depends(require_role(BanxeRole.MLRO, BanxeRole.CEO))
    """

    async def _check(
        identity: UserIdentity = FastAPISecurity(require_auth),
    ) -> UserIdentity:
        if not any(identity.has_role(r) for r in roles):
            role_names = ", ".join(r.value for r in roles)
            raise HTTPException(
                status_code=403,
                detail=f"Role required: {role_names}",
            )
        return identity

    return _check


# ── ADR-027: Audit-trail durability (BufferedAuditPort) ──────────────────────


@lru_cache(maxsize=1)
def get_buffered_audit_port() -> BufferedAuditPort:
    """Production audit sink: SQLite ring-buffer (ADR-027 step 2).

    Events are buffered in SQLite until the drain cron (step 3) flushes to ClickHouse.
    AUDIT_BUFFER_PATH → SQLite path (default: /tmp/banxe-audit-buffer.db)
    """
    from src.safeguarding.buffered_audit_port import BufferedAuditPort

    buffer_path = os.getenv("AUDIT_BUFFER_PATH", "/tmp/banxe-audit-buffer.db")  # noqa: S108  # nosec B108 — intentional default; production sets explicit path via env
    return BufferedAuditPort(db_path=buffer_path)


# ── Wave E: Crypto legacy adapter DI (ADR-031, Phase 5 Step 1) ───────────────


@lru_cache(maxsize=1)
def get_crypto_application_service():  # type: ignore[return]
    """Crypto application service — REWRITE-7/8/9 legacy adapter composition.

    CRYPTO_WALLET_ADAPTER / CRYPTO_PROCESSING_ADAPTER / CRYPTO_RPC_ADAPTER env vars
    reserved for future real-adapter selection; scaffold only for now.
    """
    from services.ledger.crypto_application_service import CryptoApplicationService
    from services.ledger.legacy.legacy_crypto_processing_adapter import (
        LegacyCryptoProcessingAdapter,
    )
    from services.ledger.legacy.legacy_crypto_rpc_adapter import LegacyCryptoRpcAdapter
    from services.ledger.legacy.legacy_crypto_wallet_adapter import LegacyCryptoWalletAdapter

    return CryptoApplicationService(
        wallet=LegacyCryptoWalletAdapter(),
        processing=LegacyCryptoProcessingAdapter(),
        rpc=LegacyCryptoRpcAdapter(),
    )


@lru_cache(maxsize=1)
def get_recon_engine() -> ReconciliationEngine:
    """Production ReconciliationEngine with durable audit sink (ADR-027 step 2).

    LEDGER_ADAPTER=stub  → StubLedgerAdapter (default, in-memory)
    LEDGER_ADAPTER=midaz → MidazLedgerAdapter (requires MIDAZ_BASE_URL)

    NOTE: ReconciliationEngine (CASS 15) was previously only instantiated in tests.
    This provider creates the first production wiring per ADR-027 step 2.
    """
    from services.recon.recon_engine import ReconciliationEngine

    ledger_name = os.environ.get("LEDGER_ADAPTER", "stub")
    if ledger_name == "midaz":
        ledger = MidazLedgerAdapter()
    else:
        ledger = StubLedgerAdapter()

    return ReconciliationEngine(ledger=ledger, audit=get_buffered_audit_port())
