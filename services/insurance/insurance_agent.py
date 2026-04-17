"""
services/insurance/insurance_agent.py
IL-INS-01 | Phase 26

High-level Insurance Agent — facade for MCP tools and API endpoints.
Amounts serialized as strings in all responses (I-05).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from services.insurance.claims_processor import ClaimsProcessor
from services.insurance.models import (
    CoverageType,
    InMemoryClaimStore,
    InMemoryInsuranceProductStore,
    InMemoryPolicyStore,
    InMemoryPremiumStore,
)
from services.insurance.policy_manager import PolicyManager
from services.insurance.product_catalog import ProductCatalog


def _policy_to_dict(policy: object) -> dict:
    return {
        "policy_id": policy.policy_id,  # type: ignore[attr-defined]
        "customer_id": policy.customer_id,  # type: ignore[attr-defined]
        "product_id": policy.product_id,  # type: ignore[attr-defined]
        "status": policy.status.value,  # type: ignore[attr-defined]
        "premium": str(policy.premium),  # type: ignore[attr-defined]
        "coverage_amount": str(policy.coverage_amount),  # type: ignore[attr-defined]
        "start_date": policy.start_date.isoformat(),  # type: ignore[attr-defined]
        "end_date": policy.end_date.isoformat(),  # type: ignore[attr-defined]
        "policy_number": policy.policy_number,  # type: ignore[attr-defined]
    }


def _claim_to_dict(claim: object) -> dict:
    return {
        "claim_id": claim.claim_id,  # type: ignore[attr-defined]
        "policy_id": claim.policy_id,  # type: ignore[attr-defined]
        "customer_id": claim.customer_id,  # type: ignore[attr-defined]
        "status": claim.status.value,  # type: ignore[attr-defined]
        "claimed_amount": str(claim.claimed_amount),  # type: ignore[attr-defined]
        "approved_amount": str(claim.approved_amount)
        if claim.approved_amount is not None
        else None,  # type: ignore[attr-defined]
        "description": claim.description,  # type: ignore[attr-defined]
    }


def _product_to_dict(product: object) -> dict:
    return {
        "product_id": product.product_id,  # type: ignore[attr-defined]
        "name": product.name,  # type: ignore[attr-defined]
        "coverage_type": product.coverage_type.value,  # type: ignore[attr-defined]
        "base_premium": str(product.base_premium),  # type: ignore[attr-defined]
        "max_coverage": str(product.max_coverage),  # type: ignore[attr-defined]
        "underwriter": product.underwriter.value,  # type: ignore[attr-defined]
    }


class InsuranceAgent:
    """Facade used by MCP tools and REST endpoints."""

    def __init__(self) -> None:
        product_store = InMemoryInsuranceProductStore()
        policy_store = InMemoryPolicyStore()
        premium_store = InMemoryPremiumStore()
        claim_store = InMemoryClaimStore()

        self._policy_manager = PolicyManager(
            product_store=product_store,
            policy_store=policy_store,
            premium_store=premium_store,
            claim_store=claim_store,
        )
        self._claims_processor = ClaimsProcessor(
            policy_store=policy_store,
            claim_store=claim_store,
        )
        self._catalog = ProductCatalog(store=product_store)

    def get_quote(
        self,
        customer_id: str,
        product_id: str,
        coverage_amount_str: str,
        term_days: int,
    ) -> dict:
        try:
            coverage_amount = Decimal(coverage_amount_str)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid coverage_amount: {coverage_amount_str}") from exc
        policy = self._policy_manager.quote(customer_id, product_id, coverage_amount, term_days)
        return _policy_to_dict(policy)

    def bind_policy(self, policy_id: str) -> dict:
        bound = self._policy_manager.bind(policy_id)
        active = self._policy_manager.activate(bound.policy_id)
        return _policy_to_dict(active)

    def file_claim(
        self,
        policy_id: str,
        customer_id: str,
        claimed_amount_str: str,
        description: str,
    ) -> dict:
        try:
            claimed_amount = Decimal(claimed_amount_str)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid claimed_amount: {claimed_amount_str}") from exc
        claim = self._claims_processor.file_claim(
            policy_id=policy_id,
            customer_id=customer_id,
            claimed_amount=claimed_amount,
            description=description,
            evidence_urls=[],
        )
        assessed = self._claims_processor.assess_claim(claim.claim_id)
        # For large amounts, approve_claim will return HITL_REQUIRED
        result = self._claims_processor.approve_claim(
            assessed.claim_id, claimed_amount, actor="agent"
        )
        if result.get("status") == "HITL_REQUIRED":
            return result
        return _claim_to_dict(self._claims_processor._claim_store.get(assessed.claim_id))  # type: ignore[attr-defined]

    def list_products(self, coverage_type: str = "") -> dict:
        if coverage_type:
            try:
                ct = CoverageType(coverage_type)
            except ValueError:
                return {"products": [], "error": f"Unknown coverage_type: {coverage_type}"}
            products = self._catalog._store.list_by_coverage_type(ct)  # type: ignore[attr-defined]
        else:
            products = self._catalog.list_all()
        return {"products": [_product_to_dict(p) for p in products]}


__all__ = ["InsuranceAgent"]
