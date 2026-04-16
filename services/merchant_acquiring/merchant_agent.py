"""
services/merchant_acquiring/merchant_agent.py
IL-MAG-01 | Phase 20

Merchant Agent — orchestrates acquiring flows.
L2: onboard, accept payments, settle, monitor risk
L4: suspend, terminate high-risk merchants (I-27)
"""

from __future__ import annotations

from services.merchant_acquiring.chargeback_handler import ChargebackHandler
from services.merchant_acquiring.merchant_onboarding import MerchantOnboarding
from services.merchant_acquiring.merchant_risk_scorer import MerchantRiskScorer
from services.merchant_acquiring.models import MAAuditPort
from services.merchant_acquiring.payment_gateway import PaymentGateway
from services.merchant_acquiring.settlement_engine import SettlementEngine


def _merchant_to_dict(m) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": m.id,
        "name": m.name,
        "legal_name": m.legal_name,
        "mcc": m.mcc,
        "country": m.country,
        "website": m.website,
        "status": m.status.value,
        "risk_tier": m.risk_tier.value,
        "onboarded_at": m.onboarded_at.isoformat() if m.onboarded_at else None,
        "daily_limit": str(m.daily_limit),
        "monthly_limit": str(m.monthly_limit),
    }


def _payment_to_dict(p) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": p.id,
        "merchant_id": p.merchant_id,
        "amount": str(p.amount),
        "currency": p.currency,
        "result": p.result.value,
        "card_last_four": p.card_last_four,
        "reference": p.reference,
        "requires_3ds": p.requires_3ds,
        "created_at": p.created_at.isoformat(),
        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        "acquirer_ref": p.acquirer_ref,
    }


def _settlement_to_dict(s) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": s.id,
        "merchant_id": s.merchant_id,
        "settlement_date": s.settlement_date.isoformat(),
        "gross_amount": str(s.gross_amount),
        "fees": str(s.fees),
        "net_amount": str(s.net_amount),
        "payment_count": s.payment_count,
        "status": s.status.value,
        "bank_reference": s.bank_reference,
    }


def _dispute_to_dict(d) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": d.id,
        "merchant_id": d.merchant_id,
        "payment_id": d.payment_id,
        "amount": str(d.amount),
        "currency": d.currency,
        "reason": d.reason.value,
        "status": d.status.value,
        "received_at": d.received_at.isoformat(),
        "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
        "evidence_submitted": d.evidence_submitted,
    }


def _score_to_dict(s) -> dict:  # type: ignore[no-untyped-def]
    return {
        "merchant_id": s.merchant_id,
        "computed_at": s.computed_at.isoformat(),
        "chargeback_ratio": s.chargeback_ratio,
        "volume_anomaly": s.volume_anomaly,
        "mcc_risk": s.mcc_risk,
        "overall_score": s.overall_score,
        "risk_tier": s.risk_tier.value,
    }


class MerchantAgent:
    """Orchestrates all merchant acquiring operations."""

    def __init__(
        self,
        onboarding: MerchantOnboarding,
        gateway: PaymentGateway,
        settlement: SettlementEngine,
        chargeback: ChargebackHandler,
        risk_scorer: MerchantRiskScorer,
        audit: MAAuditPort,
    ) -> None:
        self._onboarding = onboarding
        self._gateway = gateway
        self._settlement = settlement
        self._chargeback = chargeback
        self._risk_scorer = risk_scorer
        self._audit = audit

    async def onboard_merchant(
        self,
        name: str,
        legal_name: str,
        mcc: str,
        country: str,
        website: str | None,
        daily_limit_str: str,
        monthly_limit_str: str,
        actor: str,
    ) -> dict:
        m = await self._onboarding.onboard(
            name,
            legal_name,
            mcc,
            country,
            website,
            daily_limit_str,
            monthly_limit_str,
            actor,
        )
        return _merchant_to_dict(m)

    async def approve_kyb(self, merchant_id: str, actor: str) -> dict:
        m = await self._onboarding.approve_kyb(merchant_id, actor)
        return _merchant_to_dict(m)

    async def accept_payment(
        self,
        merchant_id: str,
        amount_str: str,
        currency: str,
        card_last_four: str,
        reference: str,
        actor: str,
    ) -> dict:
        p = await self._gateway.accept_payment(
            merchant_id, amount_str, currency, card_last_four, reference, actor
        )
        return _payment_to_dict(p)

    async def complete_3ds(self, payment_id: str, actor: str) -> dict:
        p = await self._gateway.complete_3ds(payment_id, actor)
        return _payment_to_dict(p)

    async def create_settlement(self, merchant_id: str, actor: str) -> dict:
        s = await self._settlement.create_settlement_batch(merchant_id, actor)
        return _settlement_to_dict(s)

    async def list_settlements(self, merchant_id: str) -> list[dict]:
        batches = await self._settlement.list_settlements(merchant_id)
        return [_settlement_to_dict(b) for b in batches]

    async def receive_chargeback(
        self,
        merchant_id: str,
        payment_id: str,
        amount_str: str,
        currency: str,
        reason: str,
        actor: str,
    ) -> dict:
        d = await self._chargeback.receive_chargeback(
            merchant_id, payment_id, amount_str, currency, reason, actor
        )
        return _dispute_to_dict(d)

    async def resolve_dispute(self, dispute_id: str, won: bool, actor: str) -> dict:
        d = await self._chargeback.resolve(dispute_id, won, actor)
        return _dispute_to_dict(d)

    async def score_merchant(self, merchant_id: str) -> dict:
        s = await self._risk_scorer.score_merchant(merchant_id)
        return _score_to_dict(s)

    async def get_merchant(self, merchant_id: str) -> dict | None:
        m = await self._onboarding.get_merchant(merchant_id)
        return _merchant_to_dict(m) if m else None

    async def list_merchants(self) -> list[dict]:
        merchants = await self._onboarding.list_merchants()
        return [_merchant_to_dict(m) for m in merchants]

    async def get_audit_log(self, merchant_id: str | None = None) -> list[dict]:
        return await self._audit.list_events(merchant_id)
