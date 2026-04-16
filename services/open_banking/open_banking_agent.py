"""
services/open_banking/open_banking_agent.py
IL-OBK-01 | Phase 15

Open Banking Agent — orchestrates PSD2 PISP/AISP flows.
L2: consent management + account info (propose, auto-execute)
L4: payment initiation (requires human approval — irreversible)
I-27: HITL gate for payment submission
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.open_banking.aisp_service import AISPService
from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    AccountAccessType,
    ASPSPRegistryPort,
    ConsentType,
    FlowType,
    OBAuditTrailPort,
)
from services.open_banking.pisp_service import PISPService
from services.open_banking.sca_orchestrator import SCAOrchestrator
from services.open_banking.token_manager import TokenManager


def _consent_to_dict(consent) -> dict:  # type: ignore[return]
    return {
        "id": consent.id,
        "type": consent.type.value,
        "aspsp_id": consent.aspsp_id,
        "entity_id": consent.entity_id,
        "permissions": [p.value for p in consent.permissions],
        "status": consent.status.value,
        "created_at": consent.created_at.isoformat(),
        "expires_at": consent.expires_at.isoformat(),
        "authorised_at": consent.authorised_at.isoformat() if consent.authorised_at else None,
        "redirect_uri": consent.redirect_uri,
    }


def _payment_to_dict(payment) -> dict:  # type: ignore[return]
    return {
        "id": payment.id,
        "consent_id": payment.consent_id,
        "entity_id": payment.entity_id,
        "aspsp_id": payment.aspsp_id,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "creditor_iban": payment.creditor_iban,
        "creditor_name": payment.creditor_name,
        "debtor_iban": payment.debtor_iban,
        "reference": payment.reference,
        "status": payment.status.value,
        "created_at": payment.created_at.isoformat(),
        "end_to_end_id": payment.end_to_end_id,
        "aspsp_payment_id": payment.aspsp_payment_id,
        "completed_at": payment.completed_at.isoformat() if payment.completed_at else None,
    }


def _account_to_dict(account) -> dict:  # type: ignore[return]
    return {
        "account_id": account.account_id,
        "aspsp_id": account.aspsp_id,
        "iban": account.iban,
        "currency": account.currency,
        "owner_name": account.owner_name,
        "balance": str(account.balance) if account.balance is not None else None,
    }


def _transaction_to_dict(txn) -> dict:  # type: ignore[return]
    return {
        "transaction_id": txn.transaction_id,
        "account_id": txn.account_id,
        "amount": str(txn.amount),
        "currency": txn.currency,
        "booking_date": txn.booking_date.isoformat(),
        "reference": txn.reference,
        "counterparty_name": txn.counterparty_name,
    }


def _aspsp_to_dict(aspsp) -> dict:  # type: ignore[return]
    return {
        "id": aspsp.id,
        "name": aspsp.name,
        "country": aspsp.country,
        "standard": aspsp.standard.value,
        "api_base_url": aspsp.api_base_url,
    }


def _event_to_dict(entry) -> dict:  # type: ignore[return]
    return {
        "id": entry.id,
        "event_type": entry.event_type,
        "entity_id": entry.entity_id,
        "consent_id": entry.consent_id,
        "payment_id": entry.payment_id,
        "details": entry.details,
        "created_at": entry.created_at.isoformat(),
        "actor": entry.actor,
    }


class OpenBankingAgent:
    """Orchestrates PSD2 PISP/AISP flows (IL-OBK-01).

    Autonomy:
    - L2 for consent management and account information (auto-execute, audit)
    - L4 for payment initiation (I-27: human approval required in production)
    """

    def __init__(
        self,
        consent_manager: ConsentManager,
        pisp_service: PISPService,
        aisp_service: AISPService,
        sca_orchestrator: SCAOrchestrator,
        token_manager: TokenManager,
        registry: ASPSPRegistryPort,
        audit: OBAuditTrailPort,
    ) -> None:
        self._consent_manager = consent_manager
        self._pisp = pisp_service
        self._aisp = aisp_service
        self._sca = sca_orchestrator
        self._token_manager = token_manager
        self._registry = registry
        self._audit = audit

    async def create_consent(
        self,
        entity_id: str,
        aspsp_id: str,
        consent_type_str: str,
        permissions_str: list[str],
        actor: str,
        redirect_uri: str | None = None,
    ) -> dict:
        """Parse inputs and create a PSD2 consent."""
        consent_type = ConsentType(consent_type_str)
        permissions = [AccountAccessType(p) for p in permissions_str]
        consent = await self._consent_manager.create_consent(
            entity_id, aspsp_id, consent_type, permissions, actor, redirect_uri
        )
        return _consent_to_dict(consent)

    async def authorise_consent(
        self,
        consent_id: str,
        auth_code: str,
        actor: str,
    ) -> dict:
        """Authorise a consent after SCA."""
        consent = await self._consent_manager.authorise_consent(consent_id, auth_code, actor)
        return _consent_to_dict(consent)

    async def revoke_consent(self, consent_id: str, actor: str) -> dict:
        """Revoke an active consent."""
        consent = await self._consent_manager.revoke_consent(consent_id, actor)
        return {"id": consent.id, "status": consent.status.value}

    async def initiate_payment(
        self,
        consent_id: str,
        entity_id: str,
        aspsp_id: str,
        amount_str: str,
        currency: str,
        creditor_iban: str,
        creditor_name: str,
        actor: str,
        debtor_iban: str | None = None,
        reference: str = "",
    ) -> dict:
        """I-27: Parse amount and initiate payment (HITL gate in production)."""
        amount = Decimal(amount_str)
        payment = await self._pisp.initiate_payment(
            consent_id=consent_id,
            entity_id=entity_id,
            aspsp_id=aspsp_id,
            amount=amount,
            currency=currency,
            creditor_iban=creditor_iban,
            creditor_name=creditor_name,
            debtor_iban=debtor_iban,
            reference=reference,
            actor=actor,
        )
        return _payment_to_dict(payment)

    async def get_accounts(self, consent_id: str, actor: str) -> list[dict]:
        """Fetch accounts for a given AISP consent."""
        accounts = await self._aisp.get_accounts(consent_id, actor)
        return [_account_to_dict(a) for a in accounts]

    async def get_transactions(
        self,
        consent_id: str,
        account_id: str,
        actor: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict]:
        """Fetch transactions for a given account."""
        txns = await self._aisp.get_transactions(consent_id, account_id, actor, from_date, to_date)
        return [_transaction_to_dict(t) for t in txns]

    async def initiate_sca(
        self,
        consent_id: str,
        flow_type_str: str,
        actor: str,
    ) -> dict:
        """Initiate an SCA challenge for the given consent."""
        flow_type = FlowType(flow_type_str)
        challenge = await self._sca.initiate_sca(consent_id, flow_type, actor)
        return {
            "id": challenge.id,
            "consent_id": challenge.consent_id,
            "flow_type": challenge.flow_type.value,
            "redirect_url": challenge.redirect_url,
            "otp_hint": challenge.otp_hint,
            "expires_at": challenge.expires_at.isoformat(),
            "completed": challenge.completed,
        }

    async def list_aspsps(self) -> list[dict]:
        """List all registered ASPSPs."""
        aspsps = await self._registry.list_all()
        return [_aspsp_to_dict(a) for a in aspsps]

    async def get_audit_log(
        self,
        entity_id: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        """Return audit log entries, optionally filtered."""
        events = await self._audit.list_events(entity_id=entity_id, event_type=event_type)
        return [_event_to_dict(e) for e in events]
