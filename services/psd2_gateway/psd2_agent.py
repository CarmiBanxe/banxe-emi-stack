"""PSD2 Agent — HITL-gated bank account access proposals.

IL-PSD2GW-01 | Phase 52B | Sprint 37
Autonomy: L4 for consent creation (COMPLIANCE_OFFICER), L1 for read operations.

HITL Gates:
  - create_consent_proposal → always L4 (COMPLIANCE_OFFICER)
  - configure_auto_pull     → always L4 (COMPLIANCE_OFFICER)
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import logging
from typing import Any

from services.psd2_gateway.adorsys_client import AdorsysClient
from services.psd2_gateway.camt053_auto_pull import AutoPuller
from services.psd2_gateway.psd2_models import (
    AccountInfo,
    BalanceResponse,
    ConsentResponse,
    InMemoryConsentStore,
    Transaction,
)

logger = logging.getLogger("banxe.psd2_gateway.agent")


class PSD2Agent:
    """PSD2 AISP/PISP agent with HITL gates for consent and pull configuration."""

    def __init__(
        self,
        client: AdorsysClient | None = None,
        puller: AutoPuller | None = None,
    ) -> None:
        self._consent_store = InMemoryConsentStore()
        self._client = client or AdorsysClient(consent_store=self._consent_store)
        self._puller = puller or AutoPuller()

    def create_consent_proposal(
        self,
        iban: str,
        access_type: str,
        valid_until: str,
        operator: str,
    ) -> dict[str, Any]:
        """Propose AISP consent creation — always HITLProposal L4 (I-27, COMPLIANCE_OFFICER).

        Bank account access requires explicit human approval.
        Returns HITLProposal — never auto-executes.
        """
        proposal_id = (
            f"psd2_cns_{hashlib.sha256(f'{iban}{valid_until}{operator}'.encode()).hexdigest()[:8]}"
        )
        return {
            "proposal_type": "HITL_REQUIRED",
            "action": "create_psd2_consent",
            "data": {
                "iban": iban[:6] + "***",  # never log full IBAN
                "access_type": access_type,
                "valid_until": valid_until,
            },
            "proposal_id": proposal_id,
            "operator": operator,
            "autonomy_level": "L4",
            "requires_approval_from": "COMPLIANCE_OFFICER",
            "reason": "PSD2 AISP bank account access requires COMPLIANCE_OFFICER approval",
            "created_at": datetime.now(UTC).isoformat(),
        }

    def get_accounts(self, consent_id: str) -> list[AccountInfo]:
        """Get accounts under an approved consent."""
        return self._client.get_accounts(consent_id)

    def get_transactions(
        self,
        consent_id: str,
        account_id: str,
        date_from: str,
        date_to: str,
    ) -> list[Transaction]:
        """Fetch bank transactions via PSD2 AISP consent. I-24 append-only."""
        return self._client.get_transactions(consent_id, account_id, date_from, date_to)

    def get_balances(self, consent_id: str, account_id: str) -> BalanceResponse:
        """Fetch account balance. Returns Decimal (I-01)."""
        return self._client.get_balances(consent_id, account_id)

    def configure_auto_pull(self, iban: str, frequency: str, operator: str) -> dict[str, Any]:
        """Propose auto-pull schedule — always HITLProposal L4 (I-27, COMPLIANCE_OFFICER)."""
        proposal_id = (
            f"psd2_pull_{hashlib.sha256(f'{iban}{frequency}{operator}'.encode()).hexdigest()[:8]}"
        )
        return {
            "proposal_type": "HITL_REQUIRED",
            "action": "configure_auto_pull",
            "data": {
                "iban": iban[:6] + "***",
                "frequency": frequency,
            },
            "proposal_id": proposal_id,
            "operator": operator,
            "autonomy_level": "L4",
            "requires_approval_from": "COMPLIANCE_OFFICER",
            "reason": "Automatic bank statement pull requires COMPLIANCE_OFFICER approval",
            "created_at": datetime.now(UTC).isoformat(),
        }

    def get_active_consents(self) -> list[ConsentResponse]:
        """Return all active (status=valid) consents from store."""
        return self._consent_store.list_active()
