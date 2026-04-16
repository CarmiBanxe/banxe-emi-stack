"""
api/routers/open_banking.py
IL-OBK-01 | Phase 15

Open Banking PSD2 Gateway REST endpoints.

POST   /open-banking/consents                  — create consent
GET    /open-banking/consents/{id}             — get consent
POST   /open-banking/consents/{id}/authorise   — authorise consent
DELETE /open-banking/consents/{id}             — revoke consent
POST   /open-banking/payments                  — initiate payment
GET    /open-banking/payments/{id}/status      — get payment status (mock)
GET    /open-banking/accounts                  — list accounts (consent_id query param)
GET    /open-banking/aspsps                    — list ASPSPs
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from services.open_banking.aisp_service import AISPService
from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    InMemoryAccountData,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
    InMemoryPaymentGateway,
    PaymentStatus,
)
from services.open_banking.open_banking_agent import OpenBankingAgent, _consent_to_dict
from services.open_banking.pisp_service import PISPService
from services.open_banking.sca_orchestrator import SCAOrchestrator
from services.open_banking.token_manager import TokenManager

router = APIRouter(prefix="/open-banking", tags=["open-banking"])


# ── Dependency factory ────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> OpenBankingAgent:
    """Build and cache the OpenBankingAgent with all InMemory stubs."""
    registry = InMemoryASPSPRegistry()
    store = InMemoryConsentStore()
    audit = InMemoryOBAuditTrail()
    gateway = InMemoryPaymentGateway(should_accept=True)
    account_data = InMemoryAccountData()

    consent_manager = ConsentManager(store=store, registry=registry, audit=audit)
    pisp = PISPService(consent_manager=consent_manager, gateway=gateway, audit=audit)
    aisp = AISPService(consent_manager=consent_manager, account_data=account_data, audit=audit)
    sca = SCAOrchestrator(consent_manager=consent_manager, audit=audit)
    token_mgr = TokenManager(registry=registry, audit=audit)

    return OpenBankingAgent(
        consent_manager=consent_manager,
        pisp_service=pisp,
        aisp_service=aisp,
        sca_orchestrator=sca,
        token_manager=token_mgr,
        registry=registry,
        audit=audit,
    )


# ── Request models ────────────────────────────────────────────────────────────


class CreateConsentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    aspsp_id: str
    entity_id: str
    consent_type: str
    permissions: list[str]
    redirect_uri: str | None = None
    actor: str


class AuthoriseConsentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    auth_code: str
    actor: str


class InitiatePaymentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    consent_id: str
    entity_id: str
    aspsp_id: str
    amount: str
    currency: str
    creditor_iban: str
    creditor_name: str
    debtor_iban: str | None = None
    reference: str = ""
    actor: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/consents")
async def create_consent(
    body: CreateConsentRequest,
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
) -> dict:
    """Create a new PSD2 consent (AWAITING_AUTHORISATION)."""
    try:
        return await agent.create_consent(
            entity_id=body.entity_id,
            aspsp_id=body.aspsp_id,
            consent_type_str=body.consent_type,
            permissions_str=body.permissions,
            actor=body.actor,
            redirect_uri=body.redirect_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/consents/{consent_id}")
async def get_consent(
    consent_id: str,
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
) -> dict:
    """Retrieve a consent by ID."""
    consent = await agent._consent_manager.get_consent(consent_id)
    if consent is None:
        raise HTTPException(status_code=404, detail=f"Consent not found: {consent_id}")
    return _consent_to_dict(consent)


@router.post("/consents/{consent_id}/authorise")
async def authorise_consent(
    consent_id: str,
    body: AuthoriseConsentRequest,
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
) -> dict:
    """Authorise a consent after SCA completion."""
    try:
        return await agent.authorise_consent(
            consent_id=consent_id,
            auth_code=body.auth_code,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/consents/{consent_id}")
async def revoke_consent(
    consent_id: str,
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
    actor: str = "system",
) -> dict:
    """Revoke an active consent."""
    try:
        return await agent.revoke_consent(consent_id=consent_id, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/payments")
async def initiate_payment(
    body: InitiatePaymentRequest,
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
) -> dict:
    """Initiate a PSD2 payment (I-27: HITL gate in production)."""
    try:
        return await agent.initiate_payment(
            consent_id=body.consent_id,
            entity_id=body.entity_id,
            aspsp_id=body.aspsp_id,
            amount_str=body.amount,
            currency=body.currency,
            creditor_iban=body.creditor_iban,
            creditor_name=body.creditor_name,
            debtor_iban=body.debtor_iban,
            reference=body.reference,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/payments/{payment_id}/status")
async def get_payment_status(payment_id: str) -> dict:
    """Return a mock payment status for the given payment ID."""
    return {
        "payment_id": payment_id,
        "status": PaymentStatus.ACCEPTED.value,
    }


@router.get("/accounts")
async def get_accounts(
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
    consent_id: Annotated[str, Query(description="Consent ID for AISP access")] = "",
    actor: str = "system",
) -> list[dict]:
    """List accounts accessible under the given AISP consent."""
    if not consent_id:
        raise HTTPException(status_code=422, detail="consent_id is required")
    try:
        return await agent.get_accounts(consent_id=consent_id, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/aspsps")
async def list_aspsps(
    agent: Annotated[OpenBankingAgent, Depends(_get_agent)],
) -> list[dict]:
    """List all registered ASPSPs."""
    return await agent.list_aspsps()
