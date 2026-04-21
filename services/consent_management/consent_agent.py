"""
services/consent_management/consent_agent.py
Consent Management Agent
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65-67, PSR 2017 Reg.112-120
Trust Zone: RED

L1 auto: validate_consent, get_consents, handle_cbpii_check.
L4 HITL: revoke_consent, initiate_pisp_payment, suspend_tpp (I-27).
"""

from __future__ import annotations

from decimal import Decimal
import logging

from services.consent_management.consent_engine import ConsentEngine
from services.consent_management.models import (
    ConsentGrant,
    ConsentScope,
    HITLProposal,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
)
from services.consent_management.psd2_flow_handler import PSD2FlowHandler
from services.consent_management.tpp_registry import TPPRegistryService

logger = logging.getLogger(__name__)


class ConsentAgent:
    """Consent Management Agent.

    L1 (auto): validate_consent, get_consents, cbpii_check.
    L4 (HITL): revoke_consent, pisp_payment, suspend_tpp (I-27).

    Protocol DI: ConsentEngine, PSD2FlowHandler, TPPRegistryService.
    """

    AUTONOMY_LEVEL = "L4"  # Most operations require human oversight

    def __init__(
        self,
        consent_engine: ConsentEngine | None = None,
        psd2_handler: PSD2FlowHandler | None = None,
        tpp_service: TPPRegistryService | None = None,
    ) -> None:
        """Initialise with injectable services (default: InMemory stubs)."""
        store = InMemoryConsentStore()
        registry = InMemoryTPPRegistry()
        audit = InMemoryAuditLog()
        self._engine = consent_engine or ConsentEngine(store, registry, audit)
        self._psd2 = psd2_handler or PSD2FlowHandler(store, registry, audit)
        self._tpp = tpp_service or TPPRegistryService(registry)

    # ── L1 Auto operations ────────────────────────────────────────────────────

    def validate_consent(self, consent_id: str, required_scope: ConsentScope) -> bool:
        """L1: Validate consent status, scope, and expiry (auto).

        Args:
            consent_id: Consent to validate.
            required_scope: Required scope.

        Returns:
            True if consent is valid.
        """
        result = self._engine.validate_consent(consent_id, required_scope)
        logger.info(
            "L1 validate_consent consent_id=%s scope=%s result=%s",
            consent_id,
            required_scope,
            result,
        )
        return result

    def get_consents(self, customer_id: str) -> list[ConsentGrant]:
        """L1: Get active consents for customer (auto).

        Args:
            customer_id: Customer identifier.

        Returns:
            List of active ConsentGrant records.
        """
        consents = self._engine.get_active_consents(customer_id)
        logger.info("L1 get_consents customer_id=%s count=%d", customer_id, len(consents))
        return consents

    def cbpii_check(self, consent_id: str, amount: Decimal) -> bool:
        """L1: Handle CBPII confirmation of funds (auto, raises on EDD threshold).

        Args:
            consent_id: Active CBPII consent.
            amount: Amount to check (Decimal, I-01).

        Returns:
            True if funds confirmed.
        """
        return self._psd2.handle_cbpii_check(consent_id, amount)

    # ── L4 HITL operations ────────────────────────────────────────────────────

    def revoke_consent(self, consent_id: str, actor: str) -> HITLProposal:
        """L4 HITL: Revoke consent — returns HITLProposal (I-27).

        Args:
            consent_id: Consent to revoke.
            actor: Requesting actor.

        Returns:
            HITLProposal requiring COMPLIANCE_OFFICER approval.
        """
        logger.warning(
            "L4 revoke_consent consent_id=%s actor=%s — HITL required", consent_id, actor
        )
        return self._engine.revoke_consent(consent_id, actor)

    def initiate_pisp_payment(self, consent_id: str, amount: Decimal, payee: str) -> HITLProposal:
        """L4 HITL: Initiate PISP payment — returns HITLProposal (I-27).

        Args:
            consent_id: Active PISP consent.
            amount: Payment amount (Decimal, I-01).
            payee: Payee identifier.

        Returns:
            HITLProposal requiring COMPLIANCE_OFFICER approval.
        """
        logger.warning(
            "L4 pisp_payment consent_id=%s amount=%s — HITL required", consent_id, amount
        )
        return self._psd2.initiate_pisp_payment(consent_id, amount, payee)

    def suspend_tpp(self, tpp_id: str, reason: str, operator: str) -> HITLProposal:
        """L4 HITL: Suspend TPP — returns HITLProposal (I-27).

        Args:
            tpp_id: TPP to suspend.
            reason: Suspension reason.
            operator: Requesting operator.

        Returns:
            HITLProposal requiring COMPLIANCE_OFFICER approval.
        """
        logger.warning("L4 suspend_tpp tpp_id=%s operator=%s — HITL required", tpp_id, operator)
        return self._tpp.suspend_tpp(tpp_id, reason, operator)
