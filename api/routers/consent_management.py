"""
api/routers/consent_management.py — Consent Management & TPP Registry endpoints
IL-CNS-01 | Phase 49 | Sprint 35

POST /v1/consent/grants                       — grant consent
GET  /v1/consent/grants/{customer_id}         — list customer consents
DELETE /v1/consent/grants/{consent_id}        — revoke consent (HITLProposal)
POST /v1/consent/validate                     — validate consent + scope
POST /v1/consent/pisp/initiate                — PISP payment (HITLProposal)
POST /v1/consent/aisp/complete                — complete AISP flow
POST /v1/consent/cbpii/check                  — confirmation of funds
GET  /v1/consent/tpps                         — list TPPs
POST /v1/consent/tpps                         — register TPP
POST /v1/consent/tpps/{tpp_id}/suspend        — suspend TPP (HITLProposal)

FCA: PSD2 Art.65-67, RTS on SCA Art.29-32, FCA PERG 15.5, PSR 2017 Reg.112-120
Trust Zone: RED
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from services.consent_management.consent_engine import ConsentEngine
from services.consent_management.consent_validator import ConsentValidator
from services.consent_management.models import (
    ConsentScope,
    ConsentType,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
    TPPType,
)
from services.consent_management.psd2_flow_handler import PSD2FlowHandler
from services.consent_management.tpp_registry import TPPRegistryService

router = APIRouter(tags=["Consent Management"])


# ── Dependency injection ──────────────────────────────────────────────────────

_shared_store = InMemoryConsentStore()
_shared_registry = InMemoryTPPRegistry()
_shared_audit = InMemoryAuditLog()


@lru_cache(maxsize=1)
def _get_consent_engine() -> ConsentEngine:
    return ConsentEngine(_shared_store, _shared_registry, _shared_audit)


@lru_cache(maxsize=1)
def _get_tpp_service() -> TPPRegistryService:
    return TPPRegistryService(_shared_registry)


@lru_cache(maxsize=1)
def _get_psd2_handler() -> PSD2FlowHandler:
    return PSD2FlowHandler(_shared_store, _shared_registry, _shared_audit)


@lru_cache(maxsize=1)
def _get_validator() -> ConsentValidator:
    return ConsentValidator(_shared_store)


# ── Request / Response models ─────────────────────────────────────────────────


class GrantConsentRequest(BaseModel):
    """Request to grant PSD2 consent."""

    customer_id: str
    tpp_id: str
    consent_type: ConsentType
    scopes: list[ConsentScope]
    ttl_days: int = 90
    transaction_limit: str | None = None  # Decimal string (I-01)
    redirect_uri: str = "https://tpp.example.com/callback"

    @field_validator("transaction_limit")
    @classmethod
    def validate_limit(cls, v: str | None) -> str | None:
        """Validate transaction_limit is valid Decimal string."""
        if v is not None:
            try:
                Decimal(v)
            except Exception:
                raise ValueError("transaction_limit must be a valid decimal string")
        return v


class ValidateConsentRequest(BaseModel):
    """Request to validate consent."""

    consent_id: str
    required_scope: ConsentScope


class PISPInitiateRequest(BaseModel):
    """Request to initiate PISP payment."""

    consent_id: str
    amount: str  # Decimal string (I-01)
    payee: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount is valid Decimal string."""
        try:
            d = Decimal(v)
            if d <= Decimal("0"):
                raise ValueError("amount must be positive")
        except Exception as exc:
            raise ValueError(f"Invalid amount: {exc}")
        return v


class AISPCompleteRequest(BaseModel):
    """Request to complete AISP flow."""

    consent_id: str
    customer_approved: bool


class CBPIICheckRequest(BaseModel):
    """Request for CBPII confirmation of funds."""

    consent_id: str
    amount: str  # Decimal string (I-01)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount is valid Decimal string."""
        try:
            Decimal(v)
        except Exception as exc:
            raise ValueError(f"Invalid amount: {exc}")
        return v


class RegisterTPPRequest(BaseModel):
    """Request to register a TPP."""

    name: str
    eidas_cert_id: str
    tpp_type: TPPType
    jurisdiction: str
    competent_authority: str


class AISPInitiateRequest(BaseModel):
    """Request to initiate AISP flow."""

    customer_id: str
    tpp_id: str
    scopes: list[ConsentScope]
    redirect_uri: str
    ttl_days: int = 90


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/consent/grants",
    status_code=201,
    summary="Grant PSD2 consent to TPP (PSD2 Art.65)",
)
def grant_consent(body: GrantConsentRequest) -> dict[str, Any]:
    """Grant PSD2 consent to a registered TPP.

    PSD2 Art.65-67: Customer must explicitly grant consent.
    TPP must be REGISTERED in the registry.
    """
    engine = _get_consent_engine()
    limit = Decimal(body.transaction_limit) if body.transaction_limit else None
    try:
        consent = engine.grant_consent(
            customer_id=body.customer_id,
            tpp_id=body.tpp_id,
            consent_type=body.consent_type,
            scopes=body.scopes,
            ttl_days=body.ttl_days,
            transaction_limit=limit,
            redirect_uri=body.redirect_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return consent.model_dump()


@router.get(
    "/consent/grants/{customer_id}",
    summary="List active consents for a customer",
)
def list_customer_consents(customer_id: str) -> list[dict[str, Any]]:
    """List all active (non-expired) consents for a customer.

    PSR 2017 Reg.113: Customers may view their active authorisations.
    """
    engine = _get_consent_engine()
    consents = engine.get_active_consents(customer_id)
    return [c.model_dump() for c in consents]


@router.delete(
    "/consent/grants/{consent_id}",
    summary="Revoke consent — returns HITLProposal (I-27)",
)
def revoke_consent(consent_id: str, actor: str = "customer") -> dict[str, Any]:
    """Revoke a consent — returns HITL proposal (irreversible, I-27).

    I-27: Revocation is irreversible — requires COMPLIANCE_OFFICER approval.
    PSD2 Art.66: Customer may withdraw consent at any time.
    """
    engine = _get_consent_engine()
    proposal = engine.revoke_consent(consent_id, actor)
    return {
        "action": proposal.action,
        "entity_id": proposal.entity_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


@router.post(
    "/consent/validate",
    summary="Validate consent scope and status",
)
def validate_consent(body: ValidateConsentRequest) -> dict[str, Any]:
    """Validate consent is active, not expired, and covers required scope.

    PSD2 Art.67: AISP must not access data beyond consent scope.
    """
    validator = _get_validator()
    is_valid = validator.is_consent_valid(body.consent_id)
    scope_ok = (
        validator.check_scope_coverage(body.consent_id, [body.required_scope])
        if is_valid
        else False
    )
    return {
        "consent_id": body.consent_id,
        "is_valid": is_valid and scope_ok,
        "status_valid": is_valid,
        "scope_covered": scope_ok,
        "required_scope": body.required_scope,
    }


@router.post(
    "/consent/pisp/initiate",
    summary="Initiate PISP payment — returns HITLProposal (I-27)",
)
def initiate_pisp_payment(body: PISPInitiateRequest) -> dict[str, Any]:
    """Initiate PISP payment — always returns HITL proposal (I-27).

    I-27: Payment initiation is always L4 HITL.
    PSD2 Art.66: PISP requires SCA and explicit consent.
    """
    handler = _get_psd2_handler()
    proposal = handler.initiate_pisp_payment(body.consent_id, Decimal(body.amount), body.payee)
    return {
        "action": proposal.action,
        "entity_id": proposal.entity_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


@router.post(
    "/consent/aisp/complete",
    summary="Complete AISP consent flow",
)
def complete_aisp_flow(body: AISPCompleteRequest) -> dict[str, Any]:
    """Complete AISP consent flow — activates or revokes consent.

    PSD2 Art.65: Customer must explicitly approve or decline AISP access.
    """
    handler = _get_psd2_handler()
    try:
        consent = handler.complete_aisp_flow(body.consent_id, body.customer_approved)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return consent.model_dump()


@router.post(
    "/consent/cbpii/check",
    summary="CBPII confirmation of funds check (PSD2 Art.65(4))",
)
def cbpii_check(body: CBPIICheckRequest) -> dict[str, Any]:
    """Check confirmation of funds for CBPII.

    PSD2 Art.65(4): Account servicing PSP must respond yes/no.
    I-04: EDD threshold £10k — amounts >= £10k raise 422.
    """
    handler = _get_psd2_handler()
    try:
        result = handler.handle_cbpii_check(body.consent_id, Decimal(body.amount))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "consent_id": body.consent_id,
        "amount": body.amount,
        "funds_available": result,
    }


@router.get(
    "/consent/tpps",
    summary="List registered TPPs",
)
def list_tpps(tpp_type: TPPType | None = None) -> list[dict[str, Any]]:
    """List all registered (active) TPPs, optionally filtered by type.

    PSR 2017 Reg.112: Account providers must recognise registered TPPs.
    """
    svc = _get_tpp_service()
    tpps = svc.list_active_tpps(tpp_type)
    return [t.model_dump() for t in tpps]


@router.post(
    "/consent/tpps",
    status_code=201,
    summary="Register a new TPP",
)
def register_tpp(body: RegisterTPPRequest) -> dict[str, Any]:
    """Register a new Third-Party Provider.

    I-02: Blocked jurisdictions (RU/BY/IR/KP/etc.) return 422.
    FCA PERG 15.5: TPPs must be authorised by a competent authority.
    """
    svc = _get_tpp_service()
    try:
        tpp = svc.register_tpp(
            name=body.name,
            eidas_cert_id=body.eidas_cert_id,
            tpp_type=body.tpp_type,
            jurisdiction=body.jurisdiction,
            competent_authority=body.competent_authority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return tpp.model_dump()


@router.post(
    "/consent/tpps/{tpp_id}/suspend",
    summary="Suspend a TPP — returns HITLProposal (I-27)",
)
def suspend_tpp(
    tpp_id: str, reason: str = "Compliance review", operator: str = "system"
) -> dict[str, Any]:
    """Suspend a TPP — returns HITL proposal (irreversible, I-27).

    I-27: TPP suspension requires COMPLIANCE_OFFICER approval.
    PSR 2017 Reg.116: TPP may be suspended for regulatory reasons.
    """
    svc = _get_tpp_service()
    proposal = svc.suspend_tpp(tpp_id, reason, operator)
    return {
        "action": proposal.action,
        "entity_id": proposal.entity_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }
