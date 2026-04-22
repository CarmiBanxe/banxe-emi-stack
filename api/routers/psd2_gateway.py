"""PSD2 Gateway Router — adorsys XS2A AISP.

IL-PSD2GW-01 | Phase 52B | Sprint 37

POST /v1/psd2/consents                               — → HITLProposal (I-27 L4, COMPLIANCE_OFFICER)
GET  /v1/psd2/accounts/{consent_id}                 — list accounts
GET  /v1/psd2/transactions/{consent_id}/{account_id} — get transactions (?date_from=&date_to=)
GET  /v1/psd2/balances/{consent_id}/{account_id}    — get balance
POST /v1/psd2/auto-pull/configure                   — → HITLProposal (I-27 L4)

FCA compliance:
  - Amounts always strings (DecimalString, I-01)
  - IBAN country check (I-02)
  - Consent creation always HITL L4 (I-27)
  - No PII in logs — IBAN masked in responses
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from services.psd2_gateway.psd2_agent import PSD2Agent
from services.psd2_gateway.psd2_models import BLOCKED_JURISDICTIONS, _iban_country

router = APIRouter(tags=["psd2-gateway"])


# ── Dependency ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> PSD2Agent:
    return PSD2Agent()


# ── Pydantic models ────────────────────────────────────────────────────────


class ConsentCreateRequest(BaseModel):
    iban: str
    access_type: str = "allAccounts"
    valid_until: str  # YYYY-MM-DD
    operator: str

    @field_validator("iban")
    @classmethod
    def validate_iban_not_blocked(cls, v: str) -> str:
        country = _iban_country(v)
        if country in BLOCKED_JURISDICTIONS:
            raise ValueError(f"I-02: IBAN from blocked jurisdiction {country!r}")
        return v


class AutoPullConfigRequest(BaseModel):
    iban: str
    frequency: str = "daily"
    operator: str

    @field_validator("iban")
    @classmethod
    def validate_iban_not_blocked(cls, v: str) -> str:
        country = _iban_country(v)
        if country in BLOCKED_JURISDICTIONS:
            raise ValueError(f"I-02: IBAN from blocked jurisdiction {country!r}")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in {"daily", "weekly"}:
            raise ValueError("frequency must be 'daily' or 'weekly'")
        return v


class BalanceResponseSchema(BaseModel):
    account_id: str
    iban: str
    currency: str
    balance_amount: str  # DecimalString (I-01)
    balance_type: str
    last_change_date_time: str


class TransactionSchema(BaseModel):
    transaction_id: str
    amount: str  # DecimalString (I-01)
    currency: str
    creditor_name: str | None
    debtor_name: str | None
    booking_date: str
    value_date: str
    reference: str | None


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/psd2/consents", status_code=202)
async def create_consent(body: ConsentCreateRequest) -> dict[str, Any]:
    """Propose PSD2 AISP consent — HITLProposal (I-27 L4, COMPLIANCE_OFFICER)."""
    agent = _get_agent()
    return agent.create_consent_proposal(
        iban=body.iban,
        access_type=body.access_type,
        valid_until=body.valid_until,
        operator=body.operator,
    )


@router.get("/psd2/accounts/{consent_id}")
async def get_accounts(consent_id: str) -> dict[str, Any]:
    """List bank accounts under an approved PSD2 consent."""
    agent = _get_agent()
    try:
        accounts = agent.get_accounts(consent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "consent_id": consent_id,
        "accounts": [
            {
                "account_id": a.account_id,
                "iban": a.iban[:6] + "***",  # mask IBAN in response
                "currency": a.currency,
                "account_type": a.account_type,
                "name": a.name,
            }
            for a in accounts
        ],
    }


@router.get("/psd2/transactions/{consent_id}/{account_id}")
async def get_transactions(
    consent_id: str,
    account_id: str,
    date_from: str = Query(description="Start date YYYY-MM-DD"),
    date_to: str = Query(description="End date YYYY-MM-DD"),
) -> dict[str, Any]:
    """Fetch bank transactions via PSD2 AISP consent. Amounts as strings (I-01)."""
    agent = _get_agent()
    try:
        txns = agent.get_transactions(consent_id, account_id, date_from, date_to)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "consent_id": consent_id,
        "account_id": account_id,
        "date_from": date_from,
        "date_to": date_to,
        "transactions": [
            TransactionSchema(
                transaction_id=t.transaction_id,
                amount=str(t.amount),  # I-01 Decimal → string
                currency=t.currency,
                creditor_name=t.creditor_name,
                debtor_name=t.debtor_name,
                booking_date=t.booking_date,
                value_date=t.value_date,
                reference=t.reference,
            ).model_dump()
            for t in txns
        ],
    }


@router.get("/psd2/balances/{consent_id}/{account_id}")
async def get_balance(consent_id: str, account_id: str) -> BalanceResponseSchema:
    """Get account balance via PSD2 AISP. Amount as string (I-01)."""
    agent = _get_agent()
    try:
        bal = agent.get_balances(consent_id, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BalanceResponseSchema(
        account_id=bal.account_id,
        iban=bal.iban[:6] + "***",  # mask IBAN
        currency=bal.currency,
        balance_amount=str(bal.balance_amount),  # I-01 Decimal → string
        balance_type=bal.balance_type,
        last_change_date_time=bal.last_change_date_time,
    )


@router.post("/psd2/auto-pull/configure", status_code=202)
async def configure_auto_pull(body: AutoPullConfigRequest) -> dict[str, Any]:
    """Propose CAMT.053 auto-pull schedule — HITLProposal (I-27 L4, COMPLIANCE_OFFICER)."""
    agent = _get_agent()
    return agent.configure_auto_pull(
        iban=body.iban,
        frequency=body.frequency,
        operator=body.operator,
    )
